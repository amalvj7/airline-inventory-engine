import threading

from app.database import SessionLocal


def run_concurrent(tasks, expect=None):
    """Run `tasks` simultaneously, each with its own session.

    Each task is a callable taking (session) and returning a result.
    Returns (results, errors).
    """
    barrier = threading.Barrier(len(tasks))
    results, errors = [], []
    lock = threading.Lock()

    def worker(task):
        with SessionLocal() as session:
            barrier.wait()
            try:
                value = task(session)
                session.commit()
                with lock:
                    results.append(value)
            except Exception as exc:
                session.rollback()
                with lock:
                    errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in tasks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results, errors




def start_concurrent(tasks):
    """Like run_concurrent, but returns (threads, results, errors) unjoined.

    Caller must join. Lets the main thread act while workers are blocked.
    """
    barrier = threading.Barrier(len(tasks))
    results, errors = [], []
    lock = threading.Lock()

    def worker(task):
        with SessionLocal() as session:
            barrier.wait()
            try:
                value = task(session)
                session.commit()
                with lock:
                    results.append(value)
            except Exception as exc:
                session.rollback()
                with lock:
                    errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in tasks]
    for t in threads:
        t.start()
    return threads, results, errors