#!/usr/bin/env python2.7
import os, sys, subprocess, argparse, time, datetime, re, shutil, tempfile, platform

# Pre-requirements that we are aware of that on some linux machines is not sometimes available by default:
prereqs = ['bison', 'flex', 'git', 'curl', 'make', 'patch', 'bzip2', 'uniq']

def startJobs(args):
  version_template = getTemplate(args)
  process_templates = alterVersions(version_template)
  (master_list, previous_progress) = getList()

  if not process_templates:
    print 'There was an error process the build templates'
    sys.exit(1)
  active_jobs = []
  # Do these sets in order (for)
  for idx, set_of_jobs in enumerate(master_list):
    # Do any job within these sets in any order (while)
    print 'On set', idx + 1, 'of', len(master_list), 'containing', len(list(set_of_jobs)), 'jobs'
    job_list = list(set_of_jobs)
    while job_list:
      for job in job_list:
        if job in previous_progress:
          print job, 'previously built. Moving on...'
          job_list.remove(job)
          continue
        if job == '':
          # Handle the dumb case of an empty set :/
          # TODO, fix this in the solverDEP define
          job_list.remove(job)
          continue
        if len(active_jobs) < int(args.max_modules):
          if not any(x[1] == job for x in active_jobs):
            print '  Launching:', job
            active_jobs.append(launchJob(job))
        else:
          # Max jobs reached, start checking for results
          break

      results = spinwait(active_jobs)
      if type(results) == type(()):
        process, module, output, delta = results
        active_jobs.remove(results)
        job_list.remove(module)
        output.seek(0)
        if process.poll():
          print output.read(), '\n\nError building', module
          killRemaining(active_jobs)
          if args.keep_failed is not True:
            deleteBuild()
          sys.exit(1)
        else:
          temp_output = output.read()
          if temp_output.find('This platform does not support') != -1:
            print '    <<<', module, '>>> not required on this platform'
          else:
            if len(job_list) == 0:
              print '   ', module, 'built. Time:', \
              str(datetime.timedelta(seconds=int(time.time()) - int(delta))), \
              'set', idx + 1, 'complete'
            else:
              print '   ',module, 'built. Time:', \
              str(datetime.timedelta(seconds=int(time.time()) - int(delta))), \
              '\n     ', len(job_list), 'job/s remaing in set. Active jobs:', \
              ' '.join([item[1] for item in active_jobs])
  return True

def spinwait(jobs):
  try:
    for job, module, output, delta in jobs:
      if job.poll() != None:
        return (job, module, output, delta)
    time.sleep(0.07)
    return
  except KeyboardInterrupt:
    print '\nCTRL-C, Exiting...'
    killRemaining(jobs)
    deleteBuild()
    sys.exit(1)

def killRemaining(process_list):
  # Loop through all active jobs and send SIGKILL
  # then try and clean up the mess afterwards

  for job, module, output, delta in process_list:
    try:
      print 'Attempting to kill active job:', module
      job.kill()
    except:
      # we really don't care about failures at this point
      pass
  return

def deleteBuild():
  # Allow 60 seconds for removing previous build directories.
  # Break out of the loop if the allotted time has passed and
  # we still have directories to remove.
  delta = int(time.time())
  print 'Removing build directories:', ' '. join(os.listdir(os.path.join(tempfile.gettempdir(),'moose_package_build_temp'))) + '...'
  while os.listdir(os.path.join(tempfile.gettempdir(),'moose_package_build_temp')) != []:
    if int(time.time()) - int(delta) > 60:
      # Times up, break out of the loop
      print 'Failed to remove all failed builds in the allotted time:', os.listdir(os.path.join(tempfile.gettempdir(),'moose_package_build_temp'))
      break
    for item_list in os.listdir(os.path.join(tempfile.gettempdir(),'moose_package_build_temp')):
      shutil.rmtree(os.path.join(tempfile.gettempdir(),'moose_package_build_temp', item_list), ignore_errors=True)
    time.sleep(1)

def solveDEP(job_list):
  progress = []
  resolved_list = []
  dependency_dict = {}
  # If a previous build detected, figure out which dependencies are no longer required
  if os.path.exists(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'progress')):
    progress_file = open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'progress'), 'r')
    progress = progress_file.read()
    progress_file.close()
    progress = progress.replace(' n/a', '')
    progress = progress.split('\n')
    progress.pop()
  for job in job_list:
    job_file = open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'packages', job), 'r')
    job_contents = job_file.read()
    job_file.close()
    # Do the actual dependency subtraction here:
    dependency_dict[job] = tuple(set(re.findall(r'DEP=\((.*)\)', job_contents)[0].split(' ')) - set(progress))

  dictionary_sets = dict((key, set(dependency_dict[key])) for key in dependency_dict)
  while dictionary_sets:
    temp_set=set(item for value in dictionary_sets.values() for item in value) - set(dictionary_sets.keys())
    temp_set.update(key for key, value in dictionary_sets.items() if not value)
    resolved_list.append(temp_set)
    dictionary_sets = dict(((key, value-temp_set) for key, value in dictionary_sets.items() if value))
  return (resolved_list, progress)

def alterVersions(version_template):
  packages_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'packages')
  if os.path.exists(packages_path) is not True:
    os.makedirs(packages_path)
  for module in os.listdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template')):
    with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template', module), 'r') as template_module:
      tmp_str = template_module.read()
    with open(os.path.join(packages_path, module), 'w') as batchfile:
      for item in version_template.iteritems():
        tmp_str = tmp_str.replace('<' + item[0] + '>', item[1])
      batchfile.write(tmp_str)
    os.chmod(os.path.join(packages_path, module), 0755)
  return True

def launchJob(module):
  t = tempfile.TemporaryFile()
  #return (subprocess.Popen([os.path.join(os.path.abspath(os.path.dirname(__file__)), 'packages', module)], stdout=t, stderr=t, shell=True), module, t, time.time())
  return (subprocess.Popen(['echo', 'test'], stdout=t, stderr=t, shell=True), module, t, time.time())

def getList():
  job_list = []
  for module in os.listdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'packages')):
    # ignore files that begin with .
    if module.find('.') != 0:
      job_list.append(module)
    else:
      print 'ignoring hidden file:', module
  return solveDEP(job_list)

def getTemplate(args):
  version_template = {}
  with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../common_files', args.me + '-version_template')) as template_file:
    template = template_file.read()
    for item in template.split('\n'):
      if len(item):
        version_template[item.split('=')[0]] = item.split('=')[1]
  return version_template

def verifyArgs(args):
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

def parseArguments(args=None):
  parser = argparse.ArgumentParser(description='Create MOOSE Environment')
  parser.add_argument('-p', '--prefix', help='Directory to install everything into')
  parser.add_argument('-m', '--max-modules', default='2', help='Specify the maximum amount of modules to run simultaneously')
  parser.add_argument('-j', '--cpu-count', default='4', help='Specify CPU count (used when make -j <number>)')
  parser.add_argument('-d', '--delete-downloads', action='store_const', const=True, default=False, help='Delete downloads when successful build completes?')
  parser.add_argument('--new-build', action='store_const', const=True, default=False, help='Start with a new build')
  parser.add_argument('--download-only', action='store_const', const=True, default=False, help='Download files used in created the package only')
  parser.add_argument('--keep-failed', action='store_const', const=True, default=False, help='Keep failed builds temporary directory')
  return verifyArgs(parser.parse_args(args))

if __name__ == '__main__':
  missing = []
  for prereq in prereqs:
    if which(prereq) is None:
      missing.append(prereq)
  if missing:
    print 'The following missing binaries would prevent some of the modules from building:', '\n\t', " ".join(missing)
    sys.exit(1)
  args = parseArguments()
  download_directory = tempfile.gettempdir() + os.path.sep + 'moose_package_download_temp'
  os.environ['RELATIVE_DIR'] = os.path.join(os.path.abspath(os.path.dirname(__file__)))
  os.environ['DOWNLOAD_DIR'] = download_directory

  if args.download_only:
    print 'Downloads will be saved to:', download_directory
    os.environ['DOWNLOAD_ONLY'] = 'True'
  else:
    os.environ['DOWNLOAD_ONLY'] = 'False'

  if args.keep_failed:
    os.environ['KEEP_FAILED'] = 'True'

  if args.new_build:
    if os.path.exists(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'progress')):
      print 'removing progress file, and started from scratch'
      os.remove(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'progress'))


  os.environ['PACKAGES_DIR'] = args.prefix
  os.environ['MOOSE_JOBS'] = args.cpu_count
  os.environ['MAX_MODULES'] = args.max_modules
  os.environ['TEMP_PREFIX'] = tempfile.gettempdir() + os.path.sep + 'moose_package_build_temp'
  os.environ['DEBUG'] = 'false'
  if not os.path.exists(download_directory):
    os.makedirs(download_directory)
  start_time = time.time()
  if startJobs(args):
    print 'All packages built.\nTotal execution time:', str(datetime.timedelta(seconds=int(time.time()) - int(start_time)))
    if args.delete_downloads:
      shutil.rmtree(os.getenv('DOWNLOAD_DIR'), ignore_errors=True)
