#!/usr/bin/env python2.7
import os, sys, argparse, platform, re, hashlib, urllib2, tarfile, tempfile, subprocess
from timeit import default_timer as clock
from signal import SIGTERM
from contrib import dag
from contrib import scheduler
from time import sleep

class Job(object):
    def __init__(self, args, package_file=None, name=None, term_width=40):
        self.args = args
        self.package_file = package_file
        self.name = name
        self.results = ''
        self._processor_count = int(args.cpu_count)
        self.__process = None
        self.__output = ''
        self.term_width = term_width

    def run(self):
        self.start_time = clock()
        t = tempfile.TemporaryFile()
        os.environ['MOOSE_JOBS'] = str(self.getAllocation())
        self.__process = subprocess.Popen([self.package_file], stdout=t, stderr=t, shell=True)
        self.__process.wait()
        self.end_time = clock()
        t.seek(0)
        self.__output = t.read()

    def getAllocation(self):
        return self._processor_count

    def setAllocation(self, count):
        self._processor_count = int(count)

    def getConcurrentModules(self):
        return self.args.max_modules

    def killJob(self):
        # Attempt to kill a running Popen process
        if self.__process is not None:
            try:
                if platform.system() == "Windows":
                    self.__process.terminate()
                else:
                    pgid = os.getpgid(self.__process.pid)
                    os.killpg(pgid, SIGTERM)
            except OSError: # Process already terminated
                pass

    def getResult(self):
        if self.__process.poll():
            print '\n', '-'*30, 'JOB FAILURE', '-'*30, '\n', self.name, '\n', self.__output
            return False
        else:
            result = '  finished    | ' + self.name
            cnt = self.term_width - len(result)
            print result, ' '*cnt, 'time: [' + '%0.2f' % float(self.end_time - self.start_time) + 's]'

# Create the Job class instances and store them as nodes in a DAG
def buildDAG(template_dir, args):
    package_dag = dag.DAG()
    for template_file in os.listdir(template_dir):
        tmp_job = Job(args, package_file=os.path.join(template_dir, template_file), name=template_file, term_width=int(args.name_length))
        package_dag.add_node(tmp_job)
    return buildEdges(package_dag, args)

# Figure out what package depends on what other package
def buildEdges(dag_object, args):
    search_dep = re.compile('DEP=\((.*)\)')
    name_to_object = {}
    for node in dag_object.topological_sort():
        name_to_object[node.name] = node

    for node in dag_object.topological_sort():
        with open(node.package_file, 'r') as f:
            content = f.read()
        deps = search_dep.findall(content)[0].split()
        for dep in deps:
            dag_object.add_edge(name_to_object[dep], name_to_object[node.name])
    return buildOnly(dag_object, args)

# Remove packages the user is not interested in building
def buildOnly(dag_object, args):
    if args.build_only:
        preds = set([])
        for package in dag_object.topological_sort():
            if package.name == args.build_only:
                preds = dag_object.all_predecessors(dag_object.predecessors(package))
                preds.add(package)
                break
        if preds:
            for node in dag_object.topological_sort():
                if node not in preds:
                    dag_object.delete_node(node)
    return dag_object

def alterVersions(version_template, args):
    packages_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'packages')
    name_length = 0
    if os.path.exists(packages_path) is not True:
        os.makedirs(packages_path)

    for module in os.listdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template')):
        if len(module) > name_length:
            name_length = len(module)

        with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template', module), 'r') as template_module:
            tmp_str = template_module.read()

        with open(os.path.join(packages_path, module), 'w') as batchfile:
            for item in version_template.iteritems():
                tmp_str = tmp_str.replace('<' + item[0] + '>', item[1])
            batchfile.write(tmp_str)

        os.chmod(os.path.join(packages_path, module), 0755)

    # Set term_width and some buffer room based on longest length name
    args.name_length = (name_length + 20)
    return packages_path

def getTemplate(args):
  version_template = {}
  with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../common_files', args.me + '-version_template')) as template_file:
    template = template_file.read()
    for item in template.split('\n'):
      if len(item):
        version_template[item.split('=')[0]] = item.split('=')[1]
  return version_template

def verifyArgs(args):
    if args.show_available:
        for package in os.listdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template')):
            print package
        sys.exit(0)

    if platform.platform().upper().find('DARWIN') != -1:
        args.me = 'darwin'
    else:
        args.me = 'linux'
    if args.prefix is None:
        print 'You must specify a directory to install everything into'
        sys.exit(1)
    elif os.path.exists(args.prefix) is not True:
        try:
            os.makedirs(args.prefix)
        except:
            print 'The path specified does not exist. Please create this path, and chown it appropriately before continuing'
            sys.exit(1)
    else:
        try:
            test_writeable = open(os.path.join(args.prefix, 'test_write'), 'a')
            test_writeable.close()
            os.remove(os.path.join(args.prefix, 'test_write'))
        except:
            print 'Unable to write to specified prefix location. Please chown this location manually before continuing'
            sys.exit(1)

    args.prefix = args.prefix.rstrip(os.path.sep)
    return args

def parseArguments(args=None):
    parser = argparse.ArgumentParser(description='Create MOOSE Environment')
    parser.add_argument('-p', '--prefix', help='Directory to install everything into')
    parser.add_argument('-j', '--cpu-count', default='4', help='Specify MAX CPU count available')
    parser.add_argument('-m', '--max-modules', default='2', help='Specify the maximum amount of modules to run simultaneously')
    parser.add_argument('--build-only', help='Build only the necessary things up to specified package')
    parser.add_argument('--show-available', action='store_const', const=True, default=False, help='Print out the list of available packages to build')
    parser.add_argument('-d', '--delete-downloads', action='store_const', const=True, default=False, help='Delete downloads when successful build completes?')
    parser.add_argument('--new-build', action='store_const', const=True, default=False, help='Start with a new build')
    parser.add_argument('--download-only', action='store_const', const=True, default=False, help='Download files used in created the package only')
    parser.add_argument('--keep-failed', action='store_const', const=True, default=False, help='Keep failed builds temporary directory')
    return verifyArgs(parser.parse_args(args))

def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None

if __name__ == '__main__':
    # Pre-requirements that we are aware of that on some linux machines is not sometimes available by default:
    prereqs = ['bison', 'flex', 'git', 'curl', 'make', 'patch', 'bzip2', 'uniq']
    missing = []
    for prereq in prereqs:
        if which(prereq) is None:
            missing.append(prereq)
    if missing:
        print 'The following missing binaries would prevent some of the modules from building:', '\n\t', " ".join(missing)
        sys.exit(1)

    args = parseArguments()
    templates = getTemplate(args)
    packages_path = alterVersions(templates, args)

    download_directory = tempfile.gettempdir() + os.path.sep + 'moose_package_download_temp'
    os.environ['RELATIVE_DIR'] = os.path.join(os.path.abspath(os.path.dirname(__file__)))
    os.environ['DOWNLOAD_DIR'] = download_directory

    if not os.path.exists(download_directory):
        os.makedirs(download_directory)

    if args.download_only:
        print 'Downloads will be saved to:', download_directory
        os.environ['DOWNLOAD_ONLY'] = 'True'
    else:
        os.environ['DOWNLOAD_ONLY'] = 'False'

    if args.keep_failed:
        os.environ['KEEP_FAILED'] = 'True'

    os.environ['PACKAGES_DIR'] = args.prefix
    os.environ['MOOSE_JOBS'] = args.cpu_count
    os.environ['TEMP_PREFIX'] = tempfile.gettempdir() + os.path.sep + 'moose_package_build_temp'

    packages_dag = buildDAG(packages_path, args)

    if args.build_only:
        print 'Attempting to build the following specific packages:\n', ', '.join([x.name for x in packages_dag.topological_sort()])

    scheduler = scheduler.Scheduler(max_processes=int(args.cpu_count), max_slots=int(args.max_modules), term_width=int(args.name_length))
    scheduler.schedule(packages_dag)
    try:
        scheduler.waitFinish()
    except KeyboardInterrupt:
        sys.exit(1)
