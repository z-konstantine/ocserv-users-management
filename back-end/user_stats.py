import os
import django
import subprocess
import re
from decimal import Decimal
from datetime import datetime


def check_stats(OcservUser, MonthlyTrafficStat, OcservUserHandler, Logger):
    logger = Logger()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ocserv stat service] ocserv stats service started")
    rx = 0
    tx = 0
    username = None
    cmd = "journalctl -fu ocserv"
    if logfile := os.environ.get("OCSERV_LOG_FILE"):
        cmd = f"tail -f {logfile}"
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ocserv stat service] receive log from: {cmd}")
    logger.log(level="info", message=f"")
    process = subprocess.Popen(cmd.split(" "), stdout=subprocess.PIPE)
    last_log_entry = "start script"
    while True:
        line = process.stdout.readline().decode().strip()
        if line.startswith(last_log_entry):
            continue
        last_log_entry = line

        search_strings = ["reason: user disconnected", "rx", "tx"]
        if all(search_string in line for search_string in search_strings):
            try:
                if main_match := re.search(r"main\[(.*?)\]", line):
                    username = main_match.group(1)
                if rx_match := re.search(r"rx: (\d+)", line):
                    rx = Decimal(float(rx_match.group(1)) / (1024**3))
                if tx_match := re.search(r"tx: (\d+)", line):
                    tx = Decimal(float(tx_match.group(1)) / (1024**3))
                if not username:
                    raise ValueError()
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ocserv stat service] username {username} disconnected. rx: {rx}, tx: {tx}")
            except Exception as e:
                logger.log(level="critical", message=e)
                logger.log(level="critical", message="unprocessable ocserv log to calculate user-rx and user-tx")
                logger.log(level="info", message=line)
                continue
            try:
                ocserv_user = OcservUser.objects.get(username=username)
                ocserv_user.rx += rx
                ocserv_user.tx += tx
                stat, _ = MonthlyTrafficStat.objects.get_or_create(
                    user=ocserv_user, year=datetime.now().year, month=datetime.now().month
                )
                stat.rx += rx
                stat.tx += tx
                stat.save()
                if (ocserv_user.traffic == OcservUser.MONTHLY and stat.tx >= ocserv_user.default_traffic) or (
                    ocserv_user.traffic == OcservUser.TOTALLY and ocserv_user.rx >= ocserv_user.default_traffic
                ):
                    user_handler = OcservUserHandler(username=ocserv_user.username)
                    result = user_handler.status_handler(active=False)
                    if result:
                        ocserv_user.active = False
                        ocserv_user.deactivate_date = datetime.now()
                        logger.log(level="info", message=f"{ocserv_user.username} is deactivated")
                    else:
                        logger.log(
                            level="critical", message=f"deactivate for user with that username ({username}) failed"
                        )
                ocserv_user.save()
            except (OcservUser.DoesNotExist, Exception) as e:
                logger.log(
                    level="warning",
                    message=f"user with that username ({username}) does not exists in db or we have error ({e})"
                )


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ocserv.settings")
    django.setup()
    from ocserv.modules.logger import Logger
    from app.models import OcservUser, MonthlyTrafficStat
    from ocserv.modules.handlers import OcservUserHandler

    check_stats(OcservUser, MonthlyTrafficStat, OcservUserHandler, Logger)
