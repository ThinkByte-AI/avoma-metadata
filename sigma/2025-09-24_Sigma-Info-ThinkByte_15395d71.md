# Sigma Info <> ThinkByte
_2025-09-24T08:30:00Z_

## Participants
- ThinkByte: Mukul M, Pavan Kalyan, Harsha Thota, Samarpith Rout, Charan Kumar
- Sigmainfo: to: Shiresha Madhury, Sandeep Phophaliya, Magesh R

## 
- URL duplication issues are being addressed by blocking parameters in the robots.txt file and by updating canonical tags to point to primary pages, ensuring uniformity across search pages.
- The current clutter of blog categories and tags on WordPress will be consolidated into around 15-20 main categories with specific drill-down tags, necessitating a manual update of existing posts.
- Meta titles for blogs need optimization by ensuring they include the target keywords, as current discrepancies might affect SEO rankings despite lengthy titles.
- Website performance issues, particularly with FCP, LCP, and TBT metrics, are under review with plans to reduce third-party scripts and optimize server responses.
- A follow-up meeting is scheduled for Wednesday to focus on UX improvements for the homepage and ecommerce pages, along with deeper insights from the UX team.

## 
- Samarpith Rout
    - Add industry-specific keywords for PES and other verticals to the keyword research document by the end of the day.
    - Confirm readiness of new blogs for publication and ensure readability scores are tracked consistently.
    - Verify the latest inspect tech heat maps to ensure the form loading correctly on fintech and other pages.
- Sandeep Phophaliya
    - Export and consolidate long tail queries from Google Search Console into the keyword research sheet and share the findings with the team.
    - Monitor and report on the quality of local leads, emphasizing strategies to increase relevant lead conversion from the US and Singapore.
    - Invite Niraj (UX lead) and Sidhu (UI designer) to the upcoming UX optimization call to address the homepage and ecommerce page issues.
- Mukul M
    - Follow up on whether the parameterized URLs are still being crawled after blocking and update the team with the findings.
    - Finalize and document the new blog category structure with a mapping sheet, then coordinate the manual update of existing blog posts’ categories and tags in WordPress.
    - Coordinate the removal of extra sitemaps from Google Search Console so that only the main sitemap (covering all pages) remains submitted.
    - Ensure that blog meta titles are updated to include the main target keywords so they match the blog titles for proper SEO.
    - Schedule and lead a UX improvement discussion targeting the homepage and ecommerce page on the next call (set for Wednesday).
    - Circulate the list of 17 landing pages with persistent crawling issues to the team for manual diagnosis and resolution.
- Magesh R
    - Recheck the effectiveness of the parameter blocking (via robots.txt) to maintain prevention of duplicate URL crawling.
    - Reassess and optimize page performance metrics (LCP, FCP, TBT) by reviewing current scores and investigating causes including third-party scripts and excessive cookies.
    - Identify and streamline ad scripts and cookie-related elements by considering consolidation into a single GTM script to improve performance.
    - Investigate the persistent crawling issues on the reported landing pages (list to be shared) and determine the root cause.
- to: Shiresha Madhury
    - Oversee the WordPress update process to ensure blog categories and tags are revised and aligned with the newly finalized structure.
    - Confirm and communicate scheduling details for the next UX meeting on Wednesday.
    - Review the list of landing pages with crawling issues (to be provided) and support the team in diagnosing the underlying problems.

## 
- Duplicate URL parameter issue (query string with a question mark and equal sign) is causing duplicate content problems and inefficient crawling.
- Noticeable performance degradation with pages taking 2-3 seconds to load, high FCP, LCP, and TBT, affecting SEO and user experience.

## 
- Discussion set in context of SEO efforts for Sigma and Lend Foundry, involving tech and SEO teams; introduction of Magesh leading multiple projects.

## 
- Manual updates for WordPress blog categories and tags are being performed; multiple sitemaps are submitted and then consolidated into a main sitemap.
- Using Google Search Console reports and inspect sessions to monitor canonical tag issues, crawling errors (including for images), and non-loading forms.

## 
- Block parameter pages via robots.txt and update canonical tags to point to the primary page; merge redundant blog categories and standardize tags using a reference sheet.
- Optimize website performance by reviewing third-party scripts and potentially consolidating them through a single GTM implementation.

## 
- Option of updating only the homepage canonical tag versus applying correct canonical tags for all pages was discussed.
- Evaluated manually updating each blog category versus standardizing them via a consolidated sheet for consistency.

## 
- Weighing the use of canonical tags versus blocking parameters via robots.txt; balancing meta title length (60 characters) with inclusion of target keywords against possible truncation.
- Removal of multiple third-party scripts in favor of a single GTM may improve performance but could affect tracking consistency.

## 
- Feedback was given to optimize meta titles to include primary keywords, ensuring consistency between the blog title and meta title.
- Sandeep Phophaliya emphasized the need to address SEO performance issues and improve lead relevance (targeting US and Singapore markets).

## 
- Planned immediate removal of extra sitemaps following the current call.
- Next UX review meeting (focusing on homepage and ecommerce page improvements) is scheduled for the next call on Wednesday.

## 
- Decision to merge redundant blog categories and update WordPress manually based on a standardized reference sheet.
- Agreed to remove extra sitemaps and consolidate into one main sitemap containing all pages.
- Set up follow-up meeting for UX testing on homepage and ecommerce pages with additional stakeholders.
- Plan to revisit and optimize website performance, including server response time checks.

## 
- Clarification needed on the increased average response time starting from September 15 and whether it signals a server issue affecting refreshed content.
- Unresolved crawling errors with certain images and landing pages require further manual diagnostics.

## 
- Risk of duplicate content negatively impacting SEO rankings if URL parameter issues are not fully resolved.
- Potential risk from performance degradation, with slow page loads affecting user experience and search rankings.

## Crawling Issues Diagnosis
- Duplicate URL parameters from search queries are causing duplicate content issues; the proposed fix is to update canonical tags on primary pages to unify these duplicates.
- Multiple sitemap submissions were identified as contributing to crawling issues. The recommendation is to remove four extra sitemaps and rely on one consolidated main sitemap.
- Certain pages continue to show persistent crawling issues despite previous fixes; these pages will be manually reviewed for root causes.

## Internal Process Improvements
- A plan was established to manually update and streamline WordPress blog categories and tags using a standardized sheet to ensure consistent SEO structure.
- Readability scores for published blogs are tracked, with current scores around 50-60; future blog performance will be monitored for iterative improvements.
- A UX review meeting for home page and ecommerce improvements has been scheduled for Wednesday to test and replicate changes across other pages.

## Blog Structure and Optimization
- Consensus to consolidate over 100 blog categories into a streamlined set of 15-20 categories, using tags for detailed drill-down topics to avoid duplicacy.
- Recommendation to align blog titles and meta titles with target keywords (within a 60-character best practice) to enhance SEO ranking.

## User Engagement Insights
- Fintech landing pages and digital blocks drive significant traffic, with Google Search Console revealing long-tail queries that suggest opportunities for content optimization.
- Lead generation remains a concern as most leads are reported irrelevant; focus on UX improvements for ecommerce and home pages is viewed as necessary to boost engagement.

## Performance Optimization Issues
- Page performance concerns were raised as static blog pages take up to 6 seconds to load, with high FCP, LCP, and TBT metrics. Discussions included optimizing third-party scripts and consolidating tag management to improve overall speed.
