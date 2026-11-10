# Tech - Delivery
_2024-09-30T08:00:00Z_

## Participants
- ThinkByte: Niharika Chavati, Vamsi Posimsetti, Anupam Gevariya, Yash Mori, Krishna Sindhur, Shivani Singamsetty, vinay kovvuri, Praneetaa Lakshmi

## Key Takeaways
- Addressed critical login flow issues, particularly OTP verification and access control, to enhance user authentication.
- Krishna Sindhur and Yash Mori emphasized the need to fix the notification system, including FCM token registration and functionality.
- Agreed on a 15-minute refresh rate for API caching to improve data accuracy and manage large datasets.
- Discussed refining integration of subscription services, payment gateways, and Google Ads API to correct fee and keyword planning errors.
- Planned a client demo of the authentication process and scheduled discussions on CICD pipeline, beta testing, and cloud migration.

## Action Items
- Krishna Sindhur
    - Ensure that the data is stored in Firebase in addition to the local database.
    - Prioritize email automation service integration.
- Speaker 2
    - Check the documentation to determine the default expiration time for the access token.
    - Work on the registration button, login flow, and UI tweaks.
- Yash Mori
    - Implement subscription and notification systems.
    - Put the remaining tasks from the product sensor list onto a separate sheet for proper listing, such as in Excel, to track progress effectively.
    - Share the link to the small Excel document for grouping tasks related to CICD and horizontal scaling dependencies.
    - List out remaining tasks in an Excel sheet.
    - Debug and fix API token issues.
    - Check the Google Ads API documentation and tutorials.
- Priti
    - Review updates on the login flow.

## Login Flow Integration Issues
- Ongoing issues with integrating the login flow using a third-party sdk, otter tailor
- Challenges with sorting out access control
- Focus on resolving the OTP issue by consulting the support team
- Difficulties accessing OTP via phone number
- Problems with distinguishing between protected and public routes
- Ensuring accurate documentation for better integration.

## Business Goals
- Complete the login flow and address issues with otp via phone number
- Ensure access control and routing between public and protected pages
- Prepare for the client's authentication process demonstration
- Implement caching for large data with a 15-minute refresh timeline
- Debug and resolve issues with the notification system and API tokens
- Integrate deep linking and Memoryfox API changes

## Current Tasks
- Working on login flow, distinguishing between protected and public routes
- Organizing and setting up access control for public and protected pages
- Connecting backend API with public and protected routes
- Updating code for other APIs and adjusting the payload
- Debugging API token issues and ensuring proper notification system functionality
- Fixing errors with Google Ads API fees and keyword planning service
- Email automation service integration for a pharma client

## Recently Completed Tasks
- Connection of several pages and backend API
- Cost and access issues sorted out
- Protected route implementation
- Caching implemented for certain models
- Notifications sent successfully despite issues with FCM token registration

## Decision
- Backend development assistance needed
- Single input text box preferred for both options on login page
- Decision outcomes support required
- Subscription and product sensor updates discussed
- CICD pipeline, beta testing, and cloud migration to be discussed
- Use of centralized Redis cluster for horizontal scaling
- Notification API to be stored in Firebase

## Authentication End-to-End Demonstration
- Team mentioned client's request to see authentication process from start to finish
- Speaker 1 will demonstrate authentication process at 5:30 PM

## Subscription and Payment Integration
- Integrate with a payment gateway
- Customize subscription services
- Conduct beta testing
- Ensure proper indexing and caching

## Task Prioritization and Dependencies
- Address necessary dependencies like CICD and horizontal scaling
- Use tools like Jira or Atlassian for project management
- Prioritize tasks like cloud migration, database indexing, and production steps for a smooth transition
- Emphasized the need to prioritize tasks

## API Caching and Data Accuracy
- Discussed the importance of caching apis to handle large datasets and ensure efficient access
- Emphasized the need for a Time-to-Live to avoid displaying outdated information and decided to implement a 15-minute refresh timeline

## Google Ads API Errors
- Errors related to fees and keyword planning services
- Conflicting versions in Github code causing errors
- Discussed errors with google ads api

## Deep Linking and Memoryfox API
- Team will focus on resolving notification issues
- Deep linking has not been integrated yet

## Pain Point
- Unable to access the token due to an issue with the OTP verification process.
- The delay in updating documentation is causing issues with the notification system triggering properly.
- The client does not want a separate button for phone number verification.

## Follow-up Meeting
- A call tomorrow to discuss weekly tasks and keep everyone updated.
- A call with the OTP support team and tech support team to be scheduled.
