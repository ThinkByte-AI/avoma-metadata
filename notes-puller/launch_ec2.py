#!/usr/bin/env python3
"""
Launch a throwaway EC2 instance (ap-south-1) that pulls Avoma AI notes straight
to S3 and TERMINATES itself when finished. Your laptop is not involved once this
returns -- the instance does Avoma -> S3 on its own.

What it does:
  1. Uploads the 3 bootstrap files to s3://<bucket>/_bootstrap/ (by file name):
        notes-puller/pull_notes.py   the puller
        data/notes/worklist.csv      precomputed 3,109-meeting work-list
        avoma api key.txt            the 10 API keys (repo root, never committed)
  2. Starts a t3.small with user-data that installs python deps, downloads those
     files, runs  pull_notes.py --s3 --worklist worklist.csv  (resumes off S3,
     so the ~180 notes already uploaded are skipped), uploads its run log to
     s3://<bucket>/_bootstrap/ec2_run.log, then `shutdown -h now`.
  3. The instance is launched with InstanceInitiatedShutdownBehavior=terminate,
     so that shutdown deletes the instance.

AWS creds for the instance are passed via user-data env (no IAM role needed);
the instance is short-lived and self-deletes. Run notes-puller/cleanup_ec2.py
afterwards to remove the _bootstrap/ files (including the keys).

Usage (run from the repo root):
    python notes-puller/launch_ec2.py
"""
import os
import sys

import boto3

BUCKET = os.environ.get("S3_BUCKET", "avoma-archive-growthbyte")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
AMI = os.environ.get("AMI_ID", "ami-0db56f446d44f2f09")   # AL2023 x86_64
ITYPE = os.environ.get("INSTANCE_TYPE", "t3.small")
BOOT = "_bootstrap"
# Local paths (relative to the repo root). Each is uploaded under its bare file
# name, which is what the instance's user-data downloads.
FILES = [os.path.join("notes-puller", "pull_notes.py"),
         os.path.join("data", "notes", "worklist.csv"),
         "avoma api key.txt"]


def load_dotenv(path=".env"):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    load_dotenv()
    ak = os.environ["AWS_ACCESS_KEY_ID"]
    sk = os.environ["AWS_SECRET_ACCESS_KEY"]

    s3 = boto3.client("s3", region_name=REGION)
    for fn in FILES:
        if not os.path.exists(fn):
            sys.exit(f"missing {fn}")
        s3.upload_file(fn, BUCKET, f"{BOOT}/{os.path.basename(fn)}")
    print(f"Uploaded bootstrap files to s3://{BUCKET}/{BOOT}/")

    # user-data: AWS creds only as env; everything else pulled from S3.
    user_data = f"""#!/bin/bash
set -x
export AWS_ACCESS_KEY_ID="{ak}"
export AWS_SECRET_ACCESS_KEY="{sk}"
export AWS_DEFAULT_REGION="{REGION}"
exec > /var/log/pullnotes.log 2>&1
dnf install -y python3-pip
pip3 install --quiet requests boto3
mkdir -p /opt/pull && cd /opt/pull
aws s3 cp "s3://{BUCKET}/{BOOT}/pull_notes.py" pull_notes.py
aws s3 cp "s3://{BUCKET}/{BOOT}/worklist.csv" worklist.csv
aws s3 cp "s3://{BUCKET}/{BOOT}/avoma api key.txt" "avoma api key.txt"
export S3_BUCKET="{BUCKET}"
export AWS_REGION="{REGION}"
( python3 pull_notes.py --s3 --worklist worklist.csv > run.log 2>&1; echo "EXIT $?" >> run.log ) || true
aws s3 cp run.log "s3://{BUCKET}/{BOOT}/ec2_run.log"
aws s3 cp /var/log/pullnotes.log "s3://{BUCKET}/{BOOT}/ec2_boot.log"
shutdown -h now
"""

    ec2 = boto3.client("ec2", region_name=REGION)
    subs = ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}])["Subnets"]
    if not subs:
        sys.exit("no default subnet found")
    subnet = subs[0]["SubnetId"]

    r = ec2.run_instances(
        ImageId=AMI, InstanceType=ITYPE, MinCount=1, MaxCount=1,
        InstanceInitiatedShutdownBehavior="terminate",
        NetworkInterfaces=[{
            "DeviceIndex": 0, "SubnetId": subnet,
            "AssociatePublicIpAddress": True,
            "DeleteOnTermination": True,
        }],
        UserData=user_data,
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [{"Key": "Name", "Value": "avoma-notes-puller"}],
        }],
        BlockDeviceMappings=[{
            "DeviceName": "/dev/xvda",
            "Ebs": {"VolumeSize": 8, "VolumeType": "gp3",
                    "DeleteOnTermination": True},
        }],
    )
    iid = r["Instances"][0]["InstanceId"]
    print(f"Launched instance: {iid}  ({ITYPE}, {REGION}, subnet {subnet})")
    print("It will self-terminate when the pull completes.")
    print(f"Monitor: notes.json count in s3://{BUCKET}/avoma/ ; "
          f"final log at s3://{BUCKET}/{BOOT}/ec2_run.log")
    print(iid)


if __name__ == "__main__":
    main()
