# Instagram Integration Setup Guide

## Overview

This guide explains how to integrate Instagram Direct Messages with your Sales Bot Platform using Meta's Graph API.

## Prerequisites

- **Instagram Business Account** (not a personal account)
- **Facebook Page** linked to your Instagram Business Account
- **Meta Developer Account** (free at [developers.facebook.com](https://developers.facebook.com))

---

## Step 1: Create Meta Developer App

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Click **"My Apps"** → **"Create App"**
3. Select **"Business"** as app type
4. Fill in app details:
   - **App Name:** Your Bot Name (e.g., "TechStore Bot")
   - **Contact Email:** Your email
5. Click **"Create App"**

---

## Step 2: Add Instagram Messaging Product

1. In your app dashboard, find **"Instagram"** in the products list
2. Click **"Set Up"** on Instagram
3. Go to **"Messenger API"** settings
4. Under **"Access Tokens"**, generate a token:
   - Select your **Facebook Page**
   - Click **"Generate Token"**
   - **Copy the token** (you'll need this for `INSTAGRAM_ACCESS_TOKEN`)

---

## Step 3: Configure Environment Variables

Add these to your `.env` file:

```bash
# Instagram Integration
INSTAGRAM_ACCESS_TOKEN=your_long_access_token_here
INSTAGRAM_VERIFY_TOKEN=any_random_string_you_choose
```

> **Note:** The `INSTAGRAM_VERIFY_TOKEN` can be any string you want - you'll use it in Step 4.

---

## Step 4: Setup Webhook

### 4.1 Expose Your Server

If running locally, use **ngrok** to expose your server:

```bash
# Start your bot server
python3 wsgi.py

# In another terminal, start ngrok
ngrok http 8080
```

Copy the `https://` URL from ngrok (e.g., `https://abc123.ngrok.io`)

### 4.2 Configure Webhook in Meta

1. In your Meta App dashboard, go to **Instagram → Messenger API → Webhooks**
2. Click **"Add Callback URL"**
3. Enter:
   - **Callback URL:** `https://your-ngrok-url.ngrok.io/webhook/instagram`
   - **Verify Token:** The same value you set in `INSTAGRAM_VERIFY_TOKEN`
4. Click **"Verify and Save"**

### 4.3 Subscribe to Events

After verification, subscribe to these webhook fields:
- ✅ `messages`
- ✅ `messaging_postbacks`
- ✅ `messaging_optins`

---

## Step 5: Link Instagram Account

1. In Meta App dashboard, go to **Instagram → Basic Display**
2. Click **"Add or Remove Instagram Business Accounts"**
3. Select your Instagram Business Account
4. Authorize the connection

---

## Step 6: Test the Integration

### Send a Test Message

1. Open Instagram app on your phone
2. Go to your Business Account profile
3. Send a DM to yourself: **"Hola"**
4. The bot should respond with a greeting

### Check Logs

```bash
# Watch server logs
tail -f logs/bot.log

# You should see:
# Instagram message from 123456789: Hola
# 📸 Instagram message sent to 123456789
```

---

## Troubleshooting

### Webhook Verification Fails

**Error:** "The callback URL or verify token couldn't be validated"

**Solution:**
- Ensure your server is running (`python3 wsgi.py`)
- Check ngrok is forwarding to the correct port
- Verify `INSTAGRAM_VERIFY_TOKEN` matches in both `.env` and Meta dashboard

### Bot Doesn't Respond

**Error:** Messages sent but no response

**Checklist:**
1. Check `INSTAGRAM_ACCESS_TOKEN` is set correctly
2. Verify Instagram Business Account is linked to the app
3. Check webhook subscriptions include `messages`
4. Review server logs for errors

### "Invalid Access Token"

**Solution:**
- Tokens expire after 60 days by default
- Generate a **Long-Lived Token** (90 days) or **Permanent Token**:
  ```bash
  curl -X GET "https://graph.facebook.com/v18.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
  ```

---

## Production Deployment

### Use Environment Variables

On Railway/Heroku/VPS, set environment variables:

```bash
# Railway
railway variables set INSTAGRAM_ACCESS_TOKEN=your_token

# Heroku
heroku config:set INSTAGRAM_ACCESS_TOKEN=your_token
```

### Update Webhook URL

When deploying to production, update the webhook URL in Meta dashboard:
- **Development:** `https://abc123.ngrok.io/webhook/instagram`
- **Production:** `https://your-domain.com/webhook/instagram`

---

## Security Best Practices

1. **Never commit tokens** to Git
2. **Use environment variables** for all secrets
3. **Rotate tokens** every 60-90 days
4. **Enable webhook signature verification** (optional but recommended)

---

## API Reference

- [Instagram Messaging API Docs](https://developers.facebook.com/docs/messenger-platform/instagram)
- [Graph API Reference](https://developers.facebook.com/docs/graph-api)
- [Webhook Setup Guide](https://developers.facebook.com/docs/messenger-platform/webhooks)

---

## Support

If you encounter issues:
1. Check [Meta Developer Community](https://developers.facebook.com/community/)
2. Review server logs: `tail -f logs/bot.log`
3. Test webhook manually: `curl -X POST https://your-url/webhook/instagram -H "Content-Type: application/json" -d '{"test": true}'`
