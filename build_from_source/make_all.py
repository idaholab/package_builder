#!/usr/bin/env python2.7
import os, sys, argparse, platform, re, hashlib, urllib2, tarfile, tempfile, subprocess, time, datetime, shutil
from signal import SIGTERM
from contrib import dag
from contrib import scheduler
import threading

# Strange behavior, see Job class's run method
global_lock = threading.Lock()

class Job(object):
    def __init__(self, args, package_file=None, name=None):
        self.args = args
        self.package_file = package_file
        self.name = name
        self.process = None
        self.__output = ''
        self.serial = False

    def run(self):
        t = tempfile.TemporaryFile()

        if self.args.dryrun:
            self.package_file = 'true'

        # Very strange behavior with threading and subprocess not returning the process
        # object immediately
        with global_lock:
            self.process = subprocess.Popen([self.package_file], stdout=t, stderr=t)

        self.process.wait()
        t.seek(0)
        self.__output = t.read()

    def killJob(self):
        # Attempt to kill a running Popen process
        if self.process is not None:
            try:
                if platform.system() == "Windows":
                    self.process.terminate()
                else:
                    pgid = os.getpgid(self.process.pid)
                    os.killpg(pgid, SIGTERM)
            except OSError: # Process already terminated
                pass

    def getResult(self):
        if self.process.poll():
            print '\n', '-'*30, 'JOB FAILURE', '-'*30, '\n', self.name, '\n', self.__output
            return False

# Create the Job class instances and store them as nodes in a DAG
def buildDAG(template_dir, args):
    package_dag = dag.DAG()
    for template_file in os.listdir(template_dir):
        tmp_job = Job(args, package_file=os.path.join(template_dir, template_file), name=template_file)
        package_dag.add_node(tmp_job)
    return buildEdges(package_dag, args)

# Figure out what package depends on what other package
def buildEdges(dag_object, args):
    search_dep = re.compile('DEP=\((.*)\)')
    serial_job = re.compile('SERIAL=True')
    name_to_object = {}
    for node in dag_object.topological_sort():
        name_to_object[node.name] = node

    for node in dag_object.topological_sort():
        with open(node.package_file, 'r') as f:
            content = f.read()
        deps = search_dep.findall(content)[0].split()

        # If this job takes no resources, set the serial flag
        if serial_job.search(content):
            node.serial = True

        for dep in deps:
            dag_object.add_edge(name_to_object[dep], name_to_object[node.name])
    return buildOnly(dag_object, args)

# Remove packages the user is not interested in building
def buildOnly(dag_object, args):
    if args.build_only:
        if args.build_only not in [x.name for x in dag_object.topological_sort()]:
            print 'specified package not available to be built', args.build_only
            sys.exit(1)
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

    if os.path.exists(packages_path) is not True and not args.dryrun:
        os.makedirs(packages_path)

    for module in os.listdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template')):
        if len(module) > name_length:
            name_length = len(module)

        with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template', module), 'r') as template_module:
            tmp_str = template_module.read()

            if not args.dryrun:
                with open(os.path.join(packages_path, module), 'w') as batchfile:
                    # Substitute base line environment variables
                    for env_var, value in args.baseline_vars:
                        if value:
                            tmp_str = tmp_str.replace('<' + env_var + '>', value)

                    # Substitute module names and versions
                    for module_key, module_name in version_template.iteritems():
                        tmp_str = tmp_str.replace('<' + module_key + '>', module_name)

                    # If there are any substitutions remaining, it means this module will
                    # not be supported on this platform.
                    remaining_tags = re.findall(r'<\w+>', tmp_str)
                    for tag in remaining_tags:
                        tmp_str = tmp_str.replace(tag, '')

                    batchfile.write(tmp_str)

                os.chmod(os.path.join(packages_path, module), 0755)

    if args.dryrun:
        packages_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template')

    # Set term_width and some buffer room based on longest length name
    args.name_length = name_length
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

    if args.dryrun or args.download_only:
        return args

    if args.with_intel64 and not os.path.exists(args.with_intel64):
        print 'Intel compilers do not exist at specified location: %s' % (args.with_intel64)
        sys.exit(1)

    if args.with_intel64 and not os.path.exists(os.path.join(args.with_intel64, 'modulefiles', 'intel')):
        print 'Unfortunately when building the Intel portion of the compiler stack, I need \nthe ability to load that environment:\n\n\tmodule load intel\n\n', \
            'However, I am not detecting the presence of such a module:\n\n\t%s' % (os.path.join(args.with_intel64, 'modulefiles', 'intel')), \
            '\n\nUnfortunately creating such a module automatically is beyond this scripts \ncapabilities. What you need to do, is start with a clean', \
            'environment, then \nsource the Intel compilers and compare the difference. This difference is \nwhat needs to end up in the module.'
        sys.exit(1)

    paths = [args.prefix]
    if args.with_intel64:
        print 'Opting to build supported modules with an Intel compiler... We will separate this build accordingly.'
        paths.append(args.prefix.replace(os.path.basename(args.prefix.rstrip(os.path.sep)), os.path.basename(args.prefix.rstrip(os.path.sep) + '_intel')))

    for path in paths:
        if path is None:
            print 'You must specify a prefix directory'
            sys.exit(1)
        elif os.path.exists(path) is not True:
            try:
                os.makedirs(path)
            except:
                print 'The path specified does not exist. Please create this path, and chown it appropriately before continuing'
                sys.exit(1)
        else:
            try:
                test_writeable = open(os.path.join(path, 'test_write'), 'a')
                test_writeable.close()
                os.remove(os.path.join(path, 'test_write'))
            except:
                print 'Unable to write to specified prefix location. Please chown this location manually before continuing'
                sys.exit(1)

    if args.code_sign_name and not args.code_sign_cert:
        print 'Codesign name supplied but not a path to the certificate'
        sys.exit(1)
    elif args.code_sign_cert and not args.code_sign_name:
        print 'Codesign certificate path set, but not the name of the certificate'
        sys.exit(1)
    elif args.code_sign_cert and not os.path.exists(args.code_sign_cert):
        print 'Path to Codesign cert does not exists'
        sys.exit(1)

    args.prefix = args.prefix.rstrip(os.path.sep)
    return args

def parseArguments(args=None):
    parser = argparse.ArgumentParser(description='Create MOOSE Environment')
    parser.add_argument('-p', '--prefix', help='Directory to install everything into')
    parser.add_argument('-j', '--cpu-count', default='4', help='Specify MAX CPU count available')
    parser.add_argument('-m', '--max-modules', default='2', help='Specify the maximum amount of modules to run simultaneously')
    parser.add_argument('--with-intel64', nargs='?', const='/opt/intel', default=None, help='Enable Intel compilers. Specify root path to Intel compilers or leave blank to default to /opt/intel')
    parser.add_argument('--code-sign-name', help='Keychain code signing certificate name available to sign LLDB with (OS X Only)')
    parser.add_argument('--code-sign-cert', help='Path to code signing certificate to include for redistribution (for use with OS X codesign)')
    parser.add_argument('--build-only', help='Build only the necessary things up to specified package')
    parser.add_argument('--temp-dir', default=tempfile.gettempdir(), help='Use this location as my scratch area when building')
    parser.add_argument('--show-available', action='store_const', const=True, default=False, help='Print out the list of available packages to build')
    parser.add_argument('--download-only', action='store_const', const=True, default=False, help='Download files used in created the package only')
    parser.add_argument('--keep-failed', action='store_const', const=True, default=False, help='Keep failed builds temporary directory')
    parser.add_argument('--dryrun', action='store_const', const=True, default=False, help='Print what would have been built, with out actually performing any downloading/building')
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

def prepareDownloads(download_directory):
    if not os.path.exists(download_directory):
        os.makedirs(download_directory)

    # Clean previous locks if any
    if os.path.exists(os.path.join(download_directory, '.LOCKS')):
        shutil.rmtree(os.path.join(download_directory, '.LOCKS'))

def notEnough(prefix):
    drive_stats = os.statvfs(prefix)
    available = drive_stats.f_frsize * drive_stats.f_bavail
    suffixes = [("TB", 12), ("GB", 9), ("MB", 6), ("KB", 3), ("Bytes", 0)]
    multiplier = 1 << 40;
    index = 0
    while available < multiplier and multiplier > 1:
        multiplier = multiplier >> 10
        index = index + 1

    # This is 30GB
    if drive_stats.f_frsize * drive_stats.f_bavail < 30*1024*1024*1024:
        print 'Available space:', '.'.join([str(available)[:-suffixes[index][1]],
                                            str(available)[suffixes[index][1]]]), suffixes[index][0]
        return True

def getDateAndHash():
    git_hash = subprocess.Popen(["git", "rev-parse", "HEAD"], stdout=subprocess.PIPE)
    date_time = datetime.datetime.now().strftime("%Y%m%d")
    hash_version = git_hash.communicate()[0]
    if git_hash.poll() != 0:
        print 'Failed to identify hash of package_builder repository'
        sys.exit(1)
    return (date_time, hash_version)

if __name__ == '__main__':
    # Pre-requirements that we are aware of that on some linux machines is not sometimes available by default:
    prereqs = ['bison', 'flex', 'git', 'curl', 'make', 'patch', 'bzip2', 'uniq']
    missing = []
    for prereq in prereqs:
        if which(prereq) is None:
            missing.append(prereq)

    if missing and not args.dryrun:
        print 'The following missing binaries would prevent some of the modules from building:', '\n\t', " ".join(missing)
        sys.exit(1)

    args = parseArguments()
    args.baseline_vars = [('PACKAGES_DIR', args.prefix),
                          ('RELATIVE_DIR', os.path.join(os.path.abspath(os.path.dirname(__file__)))),
                          ('DOWNLOAD_DIR', os.path.join(args.temp_dir, 'moose_package_download_temp')),
                          ('DOWNLOAD_ONLY', str(args.download_only)),
                          ('TEMP_PREFIX', os.path.join(args.temp_dir, 'moose_package_build_temp')),
                          ('MOOSE_JOBS', args.cpu_count),
                          ('KEEP_FAILED', str(args.keep_failed)),
                          ('CODESIGN_NAME', args.code_sign_name),
                          ('CODESIGN_CERT', args.code_sign_cert),
                          ('WITH_INTEL', str(args.with_intel64))]

    if not args.dryrun \
       and not args.build_only \
       and args.prefix \
       and notEnough(args.prefix):
        print 'The entire package building process consumes up to 30Gb of free space.\nNot enough free space in: %s' % (args.prefix)
        sys.exit(1)

    templates = getTemplate(args)
    packages_path = alterVersions(templates, args)

    if not args.dryrun:
        prepareDownloads(os.path.join(args.temp_dir, 'moose_package_download_temp'))

    if args.download_only:
        print 'Downloads will be saved to:', os.path.join(args.temp_dir, 'moose_package_download_temp')
    else:
        (build_date, build_hash) = getDateAndHash()

    packages_dag = buildDAG(packages_path, args)

    if args.build_only:
        print 'Attempting to build the following specific packages:\n', ', '.join([x.name for x in packages_dag.topological_sort()])

    scheduler = scheduler.Scheduler(args, max_processes=int(args.cpu_count), max_slots=int(args.max_modules), term_width=int(args.name_length))
    start_time = time.time()
    scheduler.schedule(packages_dag)
    try:
        scheduler.waitFinish()
    except KeyboardInterrupt:
        pass

    if args.download_only:
        print '\nDownloads saved to: %s' %(os.path.join(args.temp_dir, 'moose_package_download_temp'))
    else:
        with open(os.path.join(args.prefix, 'build'), 'w') as build_file:
            build_file.write("BUILD_DATE:%s\nPACKAGE_BUILDER_HASH:%s" % (build_date, build_hash))

    print 'Total Time:', str(datetime.timedelta(seconds=int(time.time()) - int(start_time)))
