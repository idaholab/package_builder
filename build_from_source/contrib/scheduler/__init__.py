import subprocess
from time import sleep
from timeit import default_timer as clock
from multiprocessing.pool import ThreadPool
import threading # for thread locking and thread timers
import multiprocessing # for timeouts
from contrib import dag # contrib DAG
from signal import SIGTERM

class SchedulerError(Exception):
    pass

class Scheduler(object):
    """
    Class for launching jobs asyncronously using the contrib DAG object

    Syntax:
       my_scheduler = Scheduler(max_processes=#)
       my_scheduler.schedule(dag_object)
       my_scheduler.waitFinish()

    The object stored in the DAG should contain a run(), getAllocation(), setAllocation(int),
    getResult() and killJob() method.

    run() method contains the work you want performed.
    getAllocation() should return an integer of how many processors (slots) this job will consume.
    setAllocation(int) should allow the scheduler to set available processors to use.
    getResult() can return anything, or what ever it is you want to print when the job is done.
    killJob() should kill what ever it is 'job' is doing.

    As jobs are finished they will be assigned to a new single process pool to perform getResult().

    """
    def __init__(self, max_processes=1, max_slots=1, load_average=64, term_width=40):

        # Max processes allowed per slot
        self.processes_per_slot = int(max_processes)

        # Maximum simultaneous slots (jobs)
        self.max_slots = int(max_slots)

        # Current slot usage
        self.used_slots = 0

        # Requested average load level to stay below
        self.load_average = load_average

        # Initialize tester pool
        self.worker_pool = ThreadPool(processes=self.processes_per_slot * self.max_slots)

        # Initialize status pool to only use 1 process (to prevent status messages from getting clobbered)
        self.status_pool = ThreadPool(processes=1)

        # Thread Locking
        self.thread_lock = threading.Lock()

        # Workers in use
        self.workers_in_use = 0

        # A simple queue increment to keep track of jobs
        self.job_queue_count = 0

        # A shared dictionary of dag objects
        self.shared_dags = {}

        # A set of already queued jobs
        self.active = set([])

        # Terminal width
        self.term_width = term_width

    def killJobs(self):
        """ loop through all active jobs and call their killJob method """
        self.status_pool.close()
        self.worker_pool.close()
        for job in self.active:
            try:
                job.killJob()
            except AttributeError:
                raise SchedulerError('killJob method is not defined')
            except: # Job already terminated
                pass
        print 'killing all jobs'
        self.job_queue_count = 0

    def waitFinish(self):
        """ block until all submitted jobs in all DAGs are finished """
        while self.job_queue_count > 0:
            sleep(0.5)

        self.worker_pool.close()
        self.worker_pool.join()
        self.status_pool.close()
        self.status_pool.join()

    def statusJob(self, job):
        """ call the job's getResults method """
        try:
            if job.getAllocation() > self.processes_per_slot * self.max_slots:
                print 'INFO: %s over subscribed with %d processes' % (job, job.getAllocation())
            if job.getResult() == False:
                self.killJobs()

            self.postLaunch(job)

        except AttributeError:
            raise SchedulerError('getResult method is not defined')

    def threadTimers(self, start_timers=None, stop_timers=None):
        """ Method containing several thread pool timers """
        if start_timers:
            long_running_timer = threading.Timer(float(20),
                                                 self.handleLongRunningJobs,
                                                 (start_timers,))
            long_running_timer.start()

            return (long_running_timer,)

        # Stop any timers we started
        elif stop_timers:
            for timer in stop_timers:
                timer.cancel()

    def handleLongRunningJobs(self, job):
        """ inform the user of what jobs are currently active """
        with self.thread_lock:
            result = '  running...  | ' + job.name
            cnt = self.term_width - len(result)
            print result, ' '*cnt, 'active:', [x.name for x in self.active]

    def launchJob(self, job):
        """ call the job's run method """
        try:
            job_timer = self.threadTimers(start_timers=job)
            job.run()
            self.threadTimers(stop_timers=job_timer)

            self.queueStatus(job)

        except AttributeError:
            raise SchedulerError('run method is not defined')

    def postLaunch(self, job):
        """
        Perform post run functions such as recovering allocated slots used
        and decrementing job queue counts etc.
        """
        with self.thread_lock:
            self.job_queue_count -= 1
            self.shared_dags[job].delete_node(job)
            self.active.remove(job)

    def schedule(self, dag_object):
        """
        Account for all the jobs in the DAG and submit the DAG for
        processing.
        """
        if type(dag_object) != type(dag.DAG()):
            raise SchedulerError('schedule method requires a DAG object')

        if self.worker_pool._state:
            raise SchedulerError('scheduler is no longer accepting jobs')

        with self.thread_lock:
            self.job_queue_count += dag_object.size()
            for job in dag_object.topological_sort():
                # create pointer to DAG for every job
                self.shared_dags[job] = dag_object

        self.queueDAG(dag_object)

    def reserveAllocation(self, job, concurrent_jobs):
        """
        Return bool if there are enough resources to run job. Try to
        optimize allocated processors to this job, if we can.
        """
        with self.thread_lock:
            if job not in self.active and len(self.active) < self.max_slots:
                caveat = ''
                # Just this one job
                if len(concurrent_jobs) == 1 and len(self.active) == 0:
                    caveat = ' (job maximized)'
                    job.setAllocation(self.processes_per_slot * self.max_slots)

                # Shortfall of jobs in this group vers available slots
                elif len(concurrent_jobs) + len(self.active) < self.max_slots:
                    new_j = (self.processes_per_slot * self.max_slots) / len(concurrent_jobs)
                    caveat = ' (job optimized %d)' % (new_j)
                    job.setAllocation(new_j)

                self.active.add(job)
                print 'Launching     | ' + job.name + caveat
                return True

    def queueDAG(self, job_dag):
        """
        Continue to assign workers for jobs that have yet to launch until
        there are no more jobs.
        """
        try:
            while job_dag.size():
                concurrent_jobs = job_dag.ind_nodes()
                for job in concurrent_jobs:
                    if self.reserveAllocation(job, concurrent_jobs) and self.worker_pool._state == 0:
                        r = self.worker_pool.apply_async(self.launchJob, (job,))
                sleep(.1)

        except KeyboardInterrupt:
            self.killJobs()
            pass

    def queueStatus(self, job):
        """ Assign a worker to a status job (print results to the screen) """
        self.status_pool.apply_async(self.statusJob, (job,))
