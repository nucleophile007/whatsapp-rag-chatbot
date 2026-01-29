# 📔 My Personal Manual: Async RAG WhatsApp Bot

Listen carefully, this is not your typical boring documentation. This is a personal handbook I've put together so you can run this super-cool "AI WhatsApp Bot" without any headache. The whole thing is asynchronous, meaning everything happens smoothly in the background.

---

## 🛠️ First Things First (The Setup)

Before you do anything else, you need to create a `.env` file (just copy the template). The most important item is your **Google API Key**. Without this, nothing will move.

```bash
# Put this in your .env file
GOOGLE_API_KEY=your_gemini_key_here
```

---

## 🚀 Fire It Up (How to Run)

I have packed everything into Docker, so you don't have to break your head with dependencies. Just run this one command and relax:

```bash
docker-compose up -d
```
Until it says "Done", you can go and grab a cup of coffee.

---

## 🧠 Making It Smart (Knowledge Base)

To make the system actually intelligent, you need to feed it some data.
1. Go to the Frontend (Check `http://localhost:5173` in your browser).
2. Create a new **Collection**.
3. Upload your PDF documents.
4. Now the AI will remember everything from those files!

---

## 📱 Connecting to WhatsApp

1. Open the **WAHA Dashboard** (`http://localhost:3000`).
2. Scan the QR Code using your phone's WhatsApp.
3. Go back to your Dashboard (Frontend) and just toggle the **Groups** you want to enable.
4. Finished! Now the bot is live in those groups.

---

## 📁 What's Inside the Box? (Quick File Guide)

- `server.py` : This is the main station where all messages land.
- `workspace_engine.py` : The actual brain of the AI (Gemini + Qdrant lives here).
- `flow_engine.py` : If you want some custom automation or special flows, this is the place.
- `rag_utils.py` : The clever logic for splitting PDFs and storing them in the database.
- `frontend/` : A sharp React dashboard to control everything.

---

## ⚠️ If Things Go South (Troubleshooting)

- **AI is not replying?** : Double-check if your `GOOGLE_API_KEY` is correct or if you've hit the limit.
- **Docker is acting up?** : Just do a `docker-compose down` and then `up` again. It works most of the time.
- **Still facing issues?** : Take a look at the logs -> `docker-compose logs -f server`.

---

**That is all!** Treat the code well, and if you want to add something new, just let me know. 🚀✨
