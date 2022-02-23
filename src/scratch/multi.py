import multiprocessing
import traceback
import time

# trying to track down why the authkey was not being set on the websocketserver spawned from the flaskinterface
#  didn't manage it so moved the web socket up to be spawned by main instead

class subProcess(multiprocessing.Process):
    def __init__(self, config: dict):
        multiprocessing.Process.__init__(self)
        print("new sub")
        try:
            self._config = config
        except Exception:
            traceback.print_exc()
            quit()

    def run(self):
        while True:
            time.sleep(2)
            print("sub  ", self._config['param1'])

class newProcess(multiprocessing.Process):
    def __init__(self, config: dict):
        multiprocessing.Process.__init__(self)
        print("new proc")
        try:
            self._config = config
        except Exception:
            traceback.print_exc()
            quit()
        self._subProc = None

    def run(self):
        self._subProc = subProcess(self._config)
        self._subProc.start()
        while True:
            time.sleep(1)
            print("proc ", self._config['param1'])


def main() -> None:
    manager = multiprocessing.Manager()
    config = manager.dict()
    config['param1'] = 123

    proc = newProcess(config)
    proc.start()

    while True:
        time.sleep(3)
        config['param1'] = config['param1'] + 1

if __name__ == '__main__':
    main()


