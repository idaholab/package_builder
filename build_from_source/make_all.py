#!/usr/bin/env python
import os, sys, subprocess, argparse, time, datetime, re, shutil, tempfile

# Pre-requirements that we are aware of that on some linux machines is not sometimes available by default:
prereqs = ['bison', 'flex', 'git', 'curl', 'make', 'bc', 'patch', 'bzip2', 'uniq']

def startJobs(args):
  (master_list, previous_progress) = getList()
  version_template = getTemplate()
  active_jobs = []
  # Do these sets in order (for)
  for set_of_jobs in master_list:
    # Do any job within these sets in any order (while)
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
        if len(active_jobs) < int(args.max_jobs):
          if not any(x[1] == job for x in active_jobs):
            print '\tLaunching job', job
            active_jobs.append(launchJob(version_template, job))
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
          if args.keep_failed is not True:
            deleteBuild(module)
          killRemaining(active_jobs)
          sys.exit(1)
        else:
          temp_output = output.read()
          if temp_output.find('This platform does not support') != -1:
            print module, 'not required on this platform'
          else:
            print module, 'built. Time:', str(datetime.timedelta(seconds=int(time.time()) - int(delta)))
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
    sys.exit(1)

def killRemaining(process_list):
  # Loop through all active jobs and send SIGKILL
  # then try and clean up the mess afterwards
  for job, module, output, delta in process_list:
    try:
      print 'Attempting to kill job:', module
      job.kill()
      deleteBuild(module)
    except:
      # we really don't care about failures at this point
      pass
  return

def deleteBuild(module):
  for item_list in os.listdir(tempfile.gettempdir()):
    if item_list.find(module) != -1:
      print 'deleting temporary build directory:', tempfile.gettempdir() + os.path.sep + item_list
      shutil.rmtree(tempfile.gettempdir() + os.path.sep + item_list, ignore_errors=True)

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
    job_file = open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template', job), 'r')
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

def alterVersions(version_template, module):
  packages_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'packages')
  if os.path.exists(packages_path) is not True:
    os.makedirs(packages_path)
  with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template', module), 'r') as template_module:
    tmp_str = template_module.read()
  with open(os.path.join(packages_path, module), 'w') as batchfile:
    for item in version_template.iteritems():
      tmp_str = tmp_str.replace('<' + item[0] + '>', item[1])
    batchfile.write(tmp_str)
  os.chmod(os.path.join(packages_path, module), 0755)
  return True

def launchJob(version_template, module):
  t = tempfile.TemporaryFile()
  prepare_job = alterVersions(version_template, module)
  return (subprocess.Popen([os.path.join(os.path.abspath(os.path.dirname(__file__)), 'packages', module)], stdout=t, stderr=t, shell=True), module, t, time.time())

def getList():
  job_list = os.listdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template'))
  return solveDEP(job_list)

def getTemplate():
  version_template = {}
  with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'version_template')) as template_file:
    template = template_file.read()
    for item in template.split('\n'):
      if len(item):
        version_template[item.split('=')[0]] = item.split('=')[1]
  return version_template

def verifyArgs(args):
  if args.prefix is None:
    print 'You must specify a directory to install everything into'
    sys.exit(1)
  elif os.path.exists(args.prefix) is not True:
    print 'The path specified does not exist. Please create this path, and chown it appropriately before continuing'
    sys.exit(1)
  else:
    args.prefix = args.prefix.rstrip(os.path.sep)
    try:
      test_writeable = open(os.path.join(args.prefix, 'test_write'), 'a')
      test_writeable.close()
      os.remove(os.path.join(args.prefix, 'test_write'))
    except:
      print 'Unable to write to specified prefix location. Please chown this location manually before continuing'
      sys.exit(1)
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
  parser.add_argument('-m', '--max-jobs', default='2', help='Specify max modules to run simultaneously')
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
    os.environ['KEEP_FAILED'] = 'False'

  if args.new_build:
    if os.path.exists(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'progress')):
      print 'removing progress file, and started from scratch'
      os.remove(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'progress'))


  os.environ['PACKAGES_DIR'] = args.prefix
  os.environ['MOOSE_JOBS'] = args.cpu_count
  os.environ['MAX_JOBS'] = args.max_jobs
  os.environ['TEMP_PREFIX'] = tempfile.gettempdir()
  os.environ['DEBUG'] = 'false'
  if not os.path.exists(download_directory):
    os.makedirs(download_directory)
  start_time = time.time()
  if startJobs(args):
    print 'All packages built.\nTotal execution time:', str(datetime.timedelta(seconds=int(time.time()) - int(start_time)))
    if args.delete_downloads:
      shutil.rmtree(os.getenv('DOWNLOAD_DIR'), ignore_errors=True)
