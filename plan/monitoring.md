# 🚀 To Run the Bot

cd "/Users/benjaminsaravia/Library/CloudStorage/GoogleDrive-elbenja@gmail.com/My Drive/Projects/Alpaca-Trader"
source venv/bin/activate
python3 main.py

The bot will:

- Run hourly during US market hours (9:30 AM – 4:00 PM ET)
- Analyze momentum candidates with 5 AI advisors
- Execute trades based on consensus
- Generate daily summaries at market close




# Local Machine Setup
Step 1: Create Virtual Environment

cd /Users/benjaminsaravia/Library/CloudStorage/GoogleDrive-elbenja@gmail.com/My\ Drive/Projects/Alpaca-Trader

python3 -m venv venv
source venv/bin/activate
Step 2: Install Dependencies

pip install -r requirements.txt

----

Ready to start? Just run:
source venv/bin/activate && python3 main.py



----

# View real-time logs
tail -f trading_bot.log

# Check if bot process is running
ps aux | grep main.py

# View trades executed today
cat trades.json | tail -20

# View daily summary
cat summaries/2026-04-12.md
