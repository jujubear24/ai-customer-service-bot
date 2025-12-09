# Technical Support FAQs

## Login & Authentication Issues

### I can't log in to my account

If you're having trouble logging in, try these steps:

1. Verify you're using the correct email address
2. Check if Caps Lock is on
3. Clear your browser cache and cookies
4. Try a different browser or incognito mode
5. Request a password reset

If problems persist, contact support with your account email and we'll investigate.

### I'm getting "Session Expired" errors

Session tokens expire after 24 hours of inactivity for security.
Simply log in again. If this happens frequently, ensure your browser accepts cookies and check for browser extensions that might be blocking them.

### Two-factor authentication isn't working

If your 2FA codes aren't working:

- Ensure your device time is synchronized (automatic time setting)
- Try the next code (they refresh every 30 seconds)
- Use one of your backup codes
- Contact support to reset 2FA if needed

## Performance Issues

### The service is running slowly

Slow performance can be caused by:

- Heavy server load during peak hours (typically 9 AM - 5 PM EST)
- Large file processing (try smaller files)
- Network connectivity issues (check your internet speed)
- Browser extensions interfering with the service

Pro tip: Processing times are typically 50% faster during off-peak hours.

### My upload keeps failing

Upload failures are usually caused by:

- File size exceeding your plan limit (Free: 25MB, Pro: 100MB)
- Unsupported file format
- Unstable internet connection
- Browser timeout for large files

Solution: Try compressing large files, ensure stable internet, or split files into smaller parts.

### Why did my request time out?

Requests timeout after 60 seconds. This typically happens with:

- Very large documents (>50 pages)
- Complex processing requests
- Server-side issues (rare)

For large documents, consider using our batch processing feature (Pro/Enterprise).

## Integration Issues

### API authentication errors

If you receive 401 Unauthorized errors:

1. Verify your API key is correct (no extra spaces)
2. Check that your API key hasn't expired
3. Ensure your plan includes API access (Pro/Enterprise only)
4. Verify you're using the correct endpoint for your region

API keys can be regenerated in Settings > API > Regenerate Key.

### Webhook deliveries are failing

Common webhook issues:

- Your endpoint must be publicly accessible (not localhost)
- Endpoint must respond within 10 seconds
- Endpoint must return 2xx status code
- HTTPS is required for production webhooks

Check the webhook logs in Settings > Integrations > Webhooks for specific error details.

### Rate limiting errors (429)

Rate limits by plan:

- Free: 10 requests per minute
- Pro: 100 requests per minute
- Enterprise: Custom limits

Best practices:

- Implement exponential backoff
- Cache responses where possible
- Use bulk endpoints for batch operations

## Data & Export Issues

### My export file is corrupted

If downloaded files won't open:

1. Try downloading again (network interruption)
2. Clear browser cache before downloading
3. Try a different browser
4. Check if you have the correct software to open the format

If the issue persists, our support team can generate a new export.

### Data seems to be missing

If you notice missing data:

1. Check your filters and date ranges
2. Verify the data wasn't deleted by another team member
3. Check your trash/archive folders
4. Review your data retention settings

Data syncs every 5 minutes; recent changes may take time to appear.

### I accidentally deleted important data

Deleted data goes to your Trash folder for 30 days. Go to Settings > Trash to restore. Pro users have additional backup restoration options—contact support for recovery requests.

## Mobile App Issues

### The app won't sync

Try these steps:

1. Check your internet connection
2. Force close and reopen the app
3. Log out and log back in
4. Update to the latest app version
5. Clear app cache in your device settings

### Push notifications aren't working

To enable notifications:

1. Ensure notifications are enabled in your device settings
2. Check in-app notification settings (Settings > Notifications)
3. Verify you haven't enabled Do Not Disturb
4. Try disabling and re-enabling notifications

### The app crashes on startup

If the app crashes immediately:

1. Update to the latest version
2. Restart your device
3. Reinstall the app (your data is stored in the cloud)
4. Ensure your device meets minimum requirements (iOS 14+ / Android 10+)

Contact support with your device model and OS version if crashes continue.
