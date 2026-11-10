#!/usr/bin/env python3
"""Post-run cleanup for the EC2 notes puller.

  * deletes the s3://<bucket>/_bootstrap/ files (script, worklist, AND the API
    keys -- so credentials don't linger in S3)
  * optionally fetches the instance's final run log first
  * reports whether the puller instance has terminated, and terminates it if a
    stray one is still running (e.g. the job errored before self-shutdown)

Usage (run from the repo root):
  python notes-puller/cleanup_ec2.py            # show status + final log, then delete _bootstrap
  python notes-puller/cleanup_ec2.py --keep-log # keep ec2_run.log/ec2_boot.log in S3
"""
import argparse
import os

import boto3

BUCKET = os.environ.get("S3_BUCKET", "avoma-archive-growthbyte")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
BOOT = "_bootstrap"


def load_dotenv(path=".env"):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-log", action="store_true")
    args = ap.parse_args()
    load_dotenv()
    s3 = boto3.client("s3", region_name=REGION)
    ec2 = boto3.client("ec2", region_name=REGION)

    # final log, if present
    for name in ("ec2_run.log", "ec2_boot.log"):
        try:
            body = s3.get_object(Bucket=BUCKET, Key=f"{BOOT}/{name}")["Body"].read()
            print(f"--- {name} (tail) ---")
            print(body.decode("utf-8", "replace")[-1500:])
        except s3.exceptions.NoSuchKey:
            print(f"(no {name} yet)")

    # instance status
    res = ec2.describe_instances(
        Filters=[{"Name": "tag:Name", "Values": ["avoma-notes-puller"]}])
    for r in res["Reservations"]:
        for inst in r["Instances"]:
            st = inst["State"]["Name"]
            iid = inst["InstanceId"]
            print(f"instance {iid}: {st}")
            if st in ("running", "stopped"):
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"  -> terminate requested for {iid}")

    # delete bootstrap files (keys!)
    keep = {f"{BOOT}/ec2_run.log", f"{BOOT}/ec2_boot.log"} if args.keep_log else set()
    objs = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{BOOT}/").get("Contents", [])
    to_del = [{"Key": o["Key"]} for o in objs if o["Key"] not in keep]
    if to_del:
        s3.delete_objects(Bucket=BUCKET, Delete={"Objects": to_del})
        print(f"Deleted {len(to_del)} bootstrap object(s): "
              + ", ".join(o["Key"] for o in to_del))
    else:
        print("Nothing to delete under _bootstrap/")


if __name__ == "__main__":
    main()
