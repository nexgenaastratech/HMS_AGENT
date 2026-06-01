# 🚀 Hotel Harriet WhatsApp Chatbot - Deployment Guide

Complete guide for deploying the Hotel Harriet WhatsApp chatbot on any server.

---

## 📋 Prerequisites

- **Python 3.11+** installed
- **WhatsApp Business Account** with API access
- **OpenRouter API Key** for AI responses
- **Server** (Render, AWS, Heroku, VPS, etc.)

---

## 🔧 Environment Variables

Create a `.env` file or set these environment variables on your server:

```bash
# WhatsApp API Configuration
PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_TOKEN=your_whatsapp_access_token
VERIFY_TOKEN=your_verify_token_for_webhook
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id

# OpenRouter AI Configuration
OPENROUTER_API_KEY=your_openrouter_api_key

# API Security
API_KEY=hotel-harriet-api-key-2025

# Database (Optional - for conversation history)
DB_HOST=your_db_host
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=your_db_name

# Application URLs
PUBLIC_URL=https://your-deployment-url.com
TOURIST_WEBSITE_URL=https://your-website.com/rameswaram
TOURIST_HERO_IMAGE=https://images.unsplash.com/photo-1582510003544-4d00b7f74220?w=800

# WhatsApp Flows (Optional)
FLOW_ID=your_flow_id
FLOW_ID_SERVICE=your_service_flow_id

# Shared Secret with .NET Backend
SECRET_KEY=your_secret_key_2025
HOTEL_HARRIET_TOKEN=your_backend_token
```

---

## 📦 Installation Steps

### 1. Clone Repository
```bash
git clone https://github.com/VIMAL3107/HSM_Chatbot.git
cd HSM_Chatbot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
# Copy .env.example to .env (if provided)
cp .env.example .env

# Edit .env with your credentials
nano .env
```

### 4. Run Locally (Testing)
```bash
python main.py
```

Server will start at `http://localhost:8000`

---

## 🌐 Deployment Options

### **Option 1: Render (Recommended)**

1. **Connect Repository**
   - Go to [render.com](https://render.com)
   - Create new Web Service
   - Connect your GitHub repository

2. **Configure Build**
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3.13

3. **Set Environment Variables**
   - Add all variables from `.env` in Render dashboard

4. **Deploy**
   - Render will auto-deploy on every git push

---

### **Option 2: AWS EC2**

1. **Launch EC2 Instance**
   ```bash
   # Ubuntu 22.04 recommended
   sudo apt update
   sudo apt install python3-pip python3-venv nginx
   ```

2. **Setup Application**
   ```bash
   git clone https://github.com/VIMAL3107/HSM_Chatbot.git
   cd HSM_Chatbot
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Create Systemd Service**
   ```bash
   sudo nano /etc/systemd/system/chatbot.service
   ```

   ```ini
   [Unit]
   Description=Hotel Harriet Chatbot
   After=network.target

   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/HSM_Chatbot
   Environment="PATH=/home/ubuntu/HSM_Chatbot/venv/bin"
   EnvironmentFile=/home/ubuntu/HSM_Chatbot/.env
   ExecStart=/home/ubuntu/HSM_Chatbot/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

   [Install]
   WantedBy=multi-user.target
   ```

4. **Start Service**
   ```bash
   sudo systemctl enable chatbot
   sudo systemctl start chatbot
   ```

5. **Configure Nginx**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }

       location /assets/ {
           alias /home/ubuntu/HSM_Chatbot/assets/;
       }
   }
   ```

---

### **Option 3: Heroku**

1. **Create Heroku App**
   ```bash
   heroku create your-app-name
   ```

2. **Set Environment Variables**
   ```bash
   heroku config:set PHONE_NUMBER_ID=your_value
   heroku config:set WHATSAPP_TOKEN=your_value
   # ... set all variables
   ```

3. **Deploy**
   ```bash
   git push heroku main
   ```

---

## 🔗 WhatsApp Webhook Setup

1. **Go to Meta Business Manager**
   - Navigate to WhatsApp > Configuration

2. **Set Webhook URL**
   ```
   https://your-deployment-url.com/webhook
   ```

3. **Set Verify Token**
   - Use the same value as `VERIFY_TOKEN` in your `.env`

4. **Subscribe to Events**
   - ☑️ messages
   - ☑️ message_status

---

## 📡 API Endpoints

### **Webhook (WhatsApp)**
```
GET  /webhook          - Webhook verification
POST /webhook          - Receive WhatsApp messages
```

### **Notifications (.NET Backend)**
```
POST /api/v1/send-notification
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "api_key": "hotel-harriet-api-key-2025"
}
```

**Body Examples:**

#### Send Template
```json
{
  "type": "template",
  "guest_phone": "917540062368",
  "template_name": "checkout",
  "template_lang": "en",
  "header_document_url": "https://example.com/invoice.pdf",
  "template_params": ["John Doe", "5,500"],
  "flow_token": "your_flow_token"
}
```

#### Send Text
```json
{
  "type": "text",
  "guest_phone": "917540062368",
  "message": "Your booking is confirmed!"
}
```

#### Send CTA Message
```json
{
  "type": "cta",
  "guest_phone": "917540062368",
  "button_text": "View Menu",
  "button_url": "https://your-site.com/menu",
  "footer_text": "Hotel Harriet"
}
```

### **Static Assets**
```
GET /assets/{filename}  - Serve images (food_menu.png, service_menu.png)
```

---

## 🗂️ File Structure

```
HSM_Chatbot/
├── main.py                 # FastAPI application entry
├── bot.py                  # Message processing logic
├── config.py               # Environment configuration
├── requirements.txt        # Python dependencies
├── render.yaml            # Render deployment config
├── assets/                # Static images
│   ├── food_menu.png
│   └── service_menu.png
├── services/              # Service modules
│   ├── whatsapp.py       # WhatsApp API functions
│   ├── memory.py         # Conversation storage
│   ├── button_keys.py    # Guest button key storage
│   ├── hms.py           # HMS integration
│   └── cache.py         # Caching utilities
└── utils/                # Utility modules
    └── web_search.py    # Web search functionality
```

---

## 🎯 Features Implemented

✅ **AI-Powered Responses** (OpenRouter GPT-3.5)
✅ **Transport Information** (Trains, Buses, Flights - 30+ cities)
✅ **Greeting Handling** (Warm welcome messages)
✅ **Food/Service CTAs** (Image + Text + Button with guest tokens)
✅ **Button Key Storage** (Personalized URLs from welcome template)
✅ **Tourist Guide** (Rameswaram attractions)
✅ **Static File Serving** (Images from deployment URL)
✅ **Template Messages** (Meta-approved templates)
✅ **Conversation History** (Database storage)

---

## 🧪 Testing

### Test Webhook
```bash
curl -X GET "https://your-url.com/webhook?hub.mode=subscribe&hub.verify_token=your_verify_token&hub.challenge=test"
```

### Test Notification API
```bash
curl -X POST https://your-url.com/api/v1/send-notification \
  -H "Content-Type: application/json" \
  -H "api_key: hotel-harriet-api-key-2025" \
  -d '{
    "type": "text",
    "guest_phone": "917540062368",
    "message": "Test message"
  }'
```

---

## 🔍 Troubleshooting

### Bot Not Responding
1. Check if server is running: `curl https://your-url.com/webhook`
2. Verify webhook is configured in Meta
3. Check logs for errors
4. Ensure `WHATSAPP_TOKEN` is valid

### Templates Not Working
1. Verify template is approved in Meta Business Manager
2. Check template name matches exactly
3. Ensure all required parameters are provided

### Images Not Loading
1. Verify images exist in `/assets` folder
2. Check image URLs are accessible
3. Ensure correct media type (PNG/JPG)

---

## 📞 Support

- **Repository**: [github.com/VIMAL3107/HSM_Chatbot](https://github.com/VIMAL3107/HSM_Chatbot)
- **Issues**: Create an issue on GitHub

---

## 📄 License

This project is for Hotel Harriet, Rameswaram.

---

**🎉 Your chatbot is now ready to serve guests!**
