from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()


def init_scheduler():
    """Initialize scheduled tasks: weekly crawl every Monday at 2am"""
    scheduler.start()
