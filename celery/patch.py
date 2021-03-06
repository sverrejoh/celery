import logging
import sys


def _check_logger_class():
    """Make sure process name is recorded when loggers are used."""

    from multiprocessing.process import current_process
    logging._acquireLock()
    try:
        OldLoggerClass = logging.getLoggerClass()
        if not getattr(OldLoggerClass, '_process_aware', False):

            class ProcessAwareLogger(OldLoggerClass):
                _process_aware = True

                def makeRecord(self, *args, **kwds):
                    record = OldLoggerClass.makeRecord(self, *args, **kwds)
                    record.processName = current_process()._name
                    return record
            logging.setLoggerClass(ProcessAwareLogger)
    finally:
        logging._releaseLock()

def monkeypatch():
    major, minor = sys.version_info[:2]
    if major == 2 and minor < 6: # python < 2.6
        _check_logger_class()

