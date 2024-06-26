# Maya Infobot

This is a telegram bot to monitor some aspects of Maya Protocol. 

Work in progress.

Features that are planned:
1. Alerts on price changes
2. Mimir changes and voting
3. New pools
4. Large transactions
5. Personal balance tracking
6. LP/Savers tracking

Channels:
1. Twitter
2. Telegram
3. Discord

## Live bot

[Start the bot in Telegram](https://t.me/MayaAlerts)

[Twitter Automated account](https://twitter.com/TODO)

## Commands

```/start``` – run the bot  
```/price``` – Cacao's price  
```/mimir``` – Mimir's constants  
```/pools``` – list of the best pools  
```/lp``` – list of your wallets  
```/savers``` – list of savers  

## Installation

0. Clone this repo
1. Install [Docker](https://docs.docker.com/engine/install/)
   and [Docker Compose](https://docs.docker.com/compose/install/)
2. Copy `example.env` to `.env`
3. Edit `REDIS_PASSWORD` in `.env`
4. Copy `example_config.yaml` to `config.yaml`
5. Edit there the parameter: `telegram.bot.token` (get it from @BotFather)
6. Edit there `telegram.channels.name` (your bot must be admin for that channel!)
7. Run `make start` and wait until the bot is build and run inside Docker

In brief:

```
cp example.env .env
nano .env
cp example_config.yaml config.yaml
nano config.yaml
make start
```

### Optional Dev deps

For deep performance profiling
`pip install line-profiler-pycharm`

If you use PyCharm, please mark directory "app" as a source root.

### Caveats

1. If you cannot debug on Python 3.10+, try uninstalling uvloop package `pip uninstall uvloop`. It helped me.
2. If you use PyCharm, please mark directory "app" as a source root.
3. If you experience problems with Redis, try to run analytics script and clean the database if it is too heavy.
```bash
make attach
PYTHONPATH="/app" python tools/redis_analytics.py /config/config.yaml
PYTHONPATH="/app" python tools/cleanup_tx_db.py /config/config.yaml
```

cleanup_tx_db script will remove all transactions older than 30 days.