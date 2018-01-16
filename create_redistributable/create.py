#!/usr/bin/env python2.7
import os, sys, re, argparse, shlex, shutil, subprocess, tempfile, platform, time

class PackageCreator:
  """
Base class for building packages
"""
  def __init__(self, args):
    self.args = args
    self.base_name = _base_name
    self.uname = platform.platform()
    self.arch = platform.machine()
    if self.uname.upper().find('DARWIN') != -1:
      self.me = 'darwin'
      self.version = '.'.join(platform.mac_ver()[0].split('.')[:2])
      self.release = _mac_version_to_name[self.version]
    else:
      # See if linux_distribution is going to provide anything useful
      self.me = 'linux'
      self.release, self.version, junk = [x.replace(' ', '') for x in platform.linux_distribution()]
      if self._linux_detection() is not True:
        if self.args.force is not True:
          print 'I am unable to properly determine your system release or version:', \
            '\n\t', ' '.join(platform.linux_distribution()), \
            '\nSometimes using a non-system specific version of python (like miniconda) will', \
            '\nreport platform identifiers incorrectly. Please make sure that `python` is', \
            '\n/usr/bin/python'
          sys.exit(1)
        else:
          print 'You have opted to force package creation regardless of package name.', \
            '\nThis will cause the finished package to be named non-accordingly,', \
            '\nas well as not being easily version controlled.'
          self.release = 'generic'
          self.version = '1.0'
    self.version_template = self._getVersionTemplate()
    self.redistributable_version = self._get_build_version()
    print 'incrementing to version', self.redistributable_version
    self.redistributable_name = '-'.join([self.base_name, str(self.redistributable_version)]) + '_' + \
                                '-'.join([self.release, self.version]) + '_' + \
                                self.arch + '.' + \
                                self.__class__.__name__.lower()

    self.temp_dir = tempfile.mkdtemp()

  def _linux_detection(self):
    try:
      lsb_release_process = subprocess.Popen(['lsb_release', '-a'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
      lsb_release_stdout = lsb_release_process.communicate()[0]
      for identifier in platform.linux_distribution():
        if lsb_release_stdout.find(identifier) != -1:
          return True
    except:
      # not every Linux OS has lsb_release, so we do not want to exit due to this
      print 'Warning: lsb_release binary is not installed. This _may_ cause an error', \
        '\nlater on when attempting to name the package accordingly.'
    return False

  def _getVersionTemplate(self):
    version_template = {}
    with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../common_files', self.me + '-version_template')) as template_file:
      template = template_file.read()
      for item in template.split('\n'):
        if len(item):
          version_template[item.split('=')[0]] = item.split('=')[1]
    return version_template

  # Method for maintaining the package version based on package class (pkg, rpm, deb)
  def _get_build_version(self):
    if not os.path.exists(os.path.join(args.meta_dir, self.__class__.__name__.lower(), self.release + '-' + self.version + '_build')):
      if not os.path.exists(os.path.join(args.meta_dir, self.__class__.__name__.lower())):
        try:
          os.makedirs(os.path.join(args.meta_dir, self.__class__.__name__.lower()))
        except OSError:
          print 'Failed to create versioning meta directory:', args.meta_dir
          sys.exit(1)
      with open(os.path.join(args.meta_dir, self.__class__.__name__.lower(), self.release + '-' + self.version + '_build'), 'w') as version_file:
        version_file.write('1')
      new_version = 1
    else:
      with open(os.path.join(args.meta_dir, self.__class__.__name__.lower(), self.release + '-' + self.version + '_build'), 'r+') as version_file:
        new_version = int(version_file.read()) + 1
        version_file.truncate(0)
        version_file.seek(0)
        version_file.write(str(new_version))
    with open(os.path.join(args.packages_dir, 'build'), 'w') as release_file:
      release_file.write('Package version: ' + str(new_version))
    return new_version

  def clean_up(self):
    shutil.rmtree(self.temp_dir)

  def prepare_area(self):
    try:
      shutil.copytree(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), self.__class__.__name__.lower()), \
                      os.path.join(self.temp_dir, self.__class__.__name__.lower()), symlinks=True, ignore=None)
    except os.error, err:
      print err
      return False
    return True

  def create_tarball(self):
    print 'Creating tarball...'
    tarball = subprocess.Popen(['tar', '-pzcf', os.path.join(self.temp_dir, self.__class__.__name__.lower(), 'payload.tar.gz'), os.path.sep + self.args.packages_dir])
    while tarball.poll() is None:
      time.sleep(1)
    if tarball.poll() != 0:
      print 'Error building tarball!'
      return False
    return True

  def which(self, program):
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

  def create_redistributable(self):
    return True

  def commit_version_change(self):
    return True

  def check_prereqs(self):
    return True

class DEB(PackageCreator):
  """
Class for building Debian based packages
"""
  def check_prereqs(self):
    if self.which('dpkg'):
      return True
    print 'dpkg not found! Unable to build deb packages.'
    return False

  def prepare_area(self):
    prereqs = self.check_prereqs()
    create_template = PackageCreator.prepare_area(self)
    if create_template and prereqs:
      for directory, directories, files in os.walk(os.path.join(self.temp_dir, 'deb/DEBIAN')):
        for xml_file in files:
          with open(os.path.join(self.temp_dir, 'deb/DEBIAN', xml_file), 'r+') as tmp_file:
            xml_string = tmp_file.read()
            tmp_file.truncate(0)
            tmp_file.seek(0)
            xml_string = xml_string.replace('<VERSION>', str(self.redistributable_version))
            xml_string = xml_string.replace('<PACKAGES_DIR>', self.args.packages_dir)
            tmp_file.write(xml_string)
      return True
    return False

  def create_tarball(self):
    # We need to copy files instead of using a tarball
    return self.copy_files()

  def copy_files(self):
    # Note: os.path.join drops previous paths when it encounters an absolute path
    # therefor we must trick it
    print 'Copying', self.args.packages_dir, 'to temp directory:', os.path.join(self.temp_dir, 'deb')
    os.makedirs(os.path.join(self.temp_dir, 'deb', *[x for x in os.path.dirname(self.args.packages_dir).split(os.sep)]))
    shutil.copytree(self.args.packages_dir,
                    os.path.join(self.temp_dir, 'deb', *[x for x in self.args.packages_dir.split(os.sep)]),
                    symlinks=True, ignore=None)
    return True

  def create_redistributable(self):
    print 'Building redistributable using dpkg... This can take a long time'
    os.chdir(self.temp_dir)
    package_builder = subprocess.Popen(['dpkg', '-b', 'deb'],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
    while package_builder.poll() == None:
      time.sleep(1)
    results = package_builder.communicate()
    if package_builder.poll() != 0:
      print 'There was error building the redistributable package using dpkg:\n\n', results[1]
      return False
    else:
      shutil.move(os.path.join(self.temp_dir, 'deb.deb'), os.path.join(self.args.relative_path, self.redistributable_name))
      print 'Redistributable built and available at:', os.path.join(self.args.relative_path, self.redistributable_name)
      return True

class RPM(PackageCreator):
  """
Class for building RedHat based packages
"""
  def check_prereqs(self):
    if self.which('rpmbuild'):
      return True
    print 'rpmbuild not found! Unable to build rpm packages.'
    return False

  def _get_requirements(self):
    # RPM based distros have different package names for 'fortran'
    # and libX11-devel, so try and discover exactly which package
    # that actually is
    requirements = []
    our_requirements = ['gcc-*fortran', 'lib*11-devel']
    for index, item in enumerate(our_requirements):
      rpm_process = subprocess.Popen(['rpm', '-qa', item], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      rpm_results = rpm_process.communicate()[0]
      if rpm_results:
        our_requirements[index] = '-'.join(rpm_results.split('-')[:2])
        requirements.append(our_requirements[index])
    if len(requirements) == len(our_requirements):
      return requirements
    else:
      print '\nERROR: While building the list of dependencies the final redistributable will\n' \
        'require your users to install, I could not determine the correct package names\n' \
        'to add. The following is that list:\n\n\t', \
        ' '.join(set(our_requirements) - set(requirements)), \
        '\n\nThe unfortunate reason this happens, is due to the different ways each OS\n' \
        'using RPM as its package management system can name things differently, and\n' \
        'I am simply searching for the wrong package.\n\n' \
        'The easy fix, is to edit this script, find the line: "our_requirements = " and\n' \
        'modify the contents of that list to match the correct package installed using:\n\n\t' \
        'rpm -qa <package name>\n\n' \
        'Or... perhaps you really do not have the above packages installed... In which\n' \
        'case, simply installing that package and re-running this script will suffice.\n\n'
      return False

  def prepare_area(self):
    prereqs = self.check_prereqs()
    requirements = self._get_requirements()
    create_template = PackageCreator.prepare_area(self)
    if create_template and requirements and prereqs:
      with open(os.path.join(self.temp_dir, 'rpm/SPECS/moose-compilers.spec'), 'r+') as tmp_file:
        xml_string = tmp_file.read()
        # set major_version based on spec file
        self.major_version = re.findall(r'Version: (\d.\d)', xml_string)[0]
        tmp_file.truncate(0)
        tmp_file.seek(0)
        xml_string = xml_string.replace('<VERSION>', str(self.redistributable_version))
        xml_string = xml_string.replace('<PACKAGES_DIR>', self.args.packages_dir)
        xml_string = xml_string.replace('<PACKAGES_BASENAME>', os.path.join(*[x for x in os.path.dirname(self.args.packages_dir).split(os.sep)]))
        xml_string = xml_string.replace('<PACKAGES_PARENT>', os.path.basename(self.args.packages_dir))
        xml_string = xml_string.replace('<REQUIREMENTS>', ' '.join(requirements))
        tmp_file.write(xml_string)
      for directory in ['BUILD', 'BUILDROOT', 'RPMS', 'SRPMS', 'SOURCES']:
        os.makedirs(os.path.join(self.temp_dir, 'rpm', directory))
      return True
    return False

  def create_tarball(self):
    tarball_results = PackageCreator.create_tarball(self)
    if tarball_results:
      # move tarball into position inside the SOURCES directory
      shutil.move(os.path.join(self.temp_dir, 'rpm/payload.tar.gz'), os.path.join(self.temp_dir, 'rpm/SOURCES', self.base_name + '.tar.gz' ))
      return True
    return False

  def create_redistributable(self):
    print 'Building redistributable using rpmbuild... This can take a long time'
    os.chdir(self.temp_dir)
    os.environ['NO_BRP_CHECK_RPATH'] = 'true'
    os.envrion['QA_SKIP_RPATHS'] = 'true'
    package_builder = subprocess.Popen(['QA_RPATHS=$(( 0x0001|0x0010|0x0002|0x0020 ))', 'rpmbuild', '-bb',
                                        '--define=_topdir %s' % (os.path.join(self.temp_dir, 'rpm')),
                                        os.path.join(self.temp_dir, 'rpm/SPECS/moose-compilers.spec')],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
    while package_builder.poll() == None:
      time.sleep(1)
    results = package_builder.communicate()
    if package_builder.poll() != 0:
      print 'There was error building the redistributable package using rpmbuild:\n\n', results[1]
      return False
    else:
      # There is only going to be one file in the following location
      for rpm_file in os.listdir(os.path.join(self.temp_dir, 'rpm/RPMS/x86_64/')):
        shutil.move(os.path.join(self.temp_dir, 'rpm/RPMS/x86_64', rpm_file), os.path.join(self.args.relative_path, self.redistributable_name))
      print 'Redistributable built and available at:', os.path.join(self.args.relative_path, self.redistributable_name)
      return True

class PKG(PackageCreator):
  """
Class for building Macintosh Packages
"""
  def prepare_area(self):
    create_template = PackageCreator.prepare_area(self)
    if create_template:
      for directory, directories, files in os.walk(os.path.join(self.temp_dir, 'pkg/OSX.pmdoc')):
        for xml_file in files:
          with open(os.path.join(self.temp_dir, 'pkg/OSX.pmdoc', xml_file), 'r+') as tmp_file:
            xml_string = tmp_file.read()
            tmp_file.truncate(0)
            tmp_file.seek(0)
            xml_string = xml_string.replace('<TEMP_DIR>', os.path.join(self.temp_dir, 'pkg/OSX'))
            xml_string = xml_string.replace('<MAC_VERSION>', self.version)
            xml_string = xml_string.replace('<REDISTRIBUTABLE_FILE>', self.redistributable_name)
            tmp_file.write(xml_string)

      # Iterate through the all control files that redistributable package uses during installation and
      # make some path/version specific changes based on machine type
      for html_file in ['README_Panel.html', 'Welcome_Panel.html', 'cleanup_post.sh', 'payload_post.sh', 'common_post.sh', 'environment_post.sh', 'icecream_post.sh']:
        with open(os.path.join(self.temp_dir, 'pkg/OSX', html_file), 'r+') as tmp_file:
          html_str = tmp_file.read()
          tmp_file.truncate(0)
          tmp_file.seek(0)

          # If we are only building a package for OS X El Capitan (10.11), set a special
          # switch that allows the installer to create a symbolic link to our openMP
          # implementation (DYLD_LIBRARY_PATH issue)
          if html_file == 'common_post.sh' and self.version in _need_symbolic_link:
            html_str = html_str.replace('<BOOL>', '1')
          else:
            html_str = html_str.replace('<BOOL>', '0')

          html_str = html_str.replace('<PACKAGES_DIR>', self.args.packages_dir)
          html_str = html_str.replace('<REDISTRIBUTABLE_VERSION>', 'Package version: ' + str(self.redistributable_version))

          for item_list in self.version_template.iteritems():
            html_str = html_str.replace('<' + item_list[0] + '>', item_list[1])

          tmp_file.write(html_str)
      return True
    return False

  def create_redistributable(self):
    os.chdir(self.temp_dir)
    print 'Building redistributable using PackageMaker... This can take a long time'
    package_builder = subprocess.Popen([self.args.package_maker, '--doc', os.path.join(self.temp_dir, 'pkg/OSX.pmdoc')],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       shell=False)
    while package_builder.poll() == None:
      time.sleep(1)
    results = package_builder.communicate()
    if package_builder.poll() != 0:
      print 'There was error building the redistributable package using PackageMaker:\n\n', results[1]
      return False
    elif self.args.sign:
      package_signer = subprocess.Popen(['productsign',
                                         '--sign', "Developer ID Installer: BATTELLE ENERGY ALLIANCE, LLC (J2Y4H5G88N)",
                                         os.path.join(self.temp_dir, 'osx.pkg'),
                                         os.path.join(self.args.relative_path, self.redistributable_name)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      while package_signer.poll() == None:
        time.sleep(1)
      results = package_signer.communicate()
      if package_signer.poll() != 0:
        print 'There was an error signing the package', results[1]
        return False
      else:
        os.remove(os.path.join(self.temp_dir, 'osx.pkg'))
        print self.redistributable_name, 'signed and ready for distribution'
    else:
      shutil.move(os.path.join(self.temp_dir, 'osx.pkg'), os.path.join(self.args.relative_path, 'osx.pkg'))
      print 'Redistributable built!\n', \
        'Optional: You should now sign the package using the following command:\n\n\t', \
        'productsign --sign "Developer ID Installer: BATTELLE ENERGY ALLIANCE, LLC (J2Y4H5G88N)"', \
        os.path.join(self.args.relative_path, 'osx.pkg'), os.path.join(self.args.relative_path, self.redistributable_name), \
        '\n\nOnce complete, you can verify your package has been correctly signed by running\n', \
        'the following command:\n\n\t', \
        'spctl -a -v --type install', os.path.join(self.args.relative_path, self.redistributable_name), \
        '\n\nIf you choose not to sign your package, the package is currently located at:\n\n\t', \
        os.path.join(self.args.relative_path, 'osx.pkg'), '\n'
    return True

def verifyArgs(args):
  fail = False

  # Try to determine package type, unless provided by the user
  if args.package_type is None:
    for package_type, arch_list in _pathetic_dict.iteritems():
      for arch in arch_list:
        if arch in platform.platform().upper():
          args.package_type = package_type
  else:
    for package_type, arch_list in _pathetic_dict.iteritems():
      if package_type.__name__ == args.package_type.upper():
        args.package_type = package_type

  # Package type is still none?
  if args.package_type is None:
    print 'Unable to determine package type. You must provide package type manually.\n' \
      'See --help for supported package types'
    fail = True

  # Add _package_maker to argparser namespace for easy access
  args.package_maker = _package_maker

  # Add absolute path location of execution script to
  # argparser namespace for easy access
  args.relative_path = os.path.abspath(os.path.dirname(sys.argv[0]))

  # Check to see if Package Maker even exists. Its the
  # point to this script after all
  if args.package_type == PKG and not os.path.exists(args.package_maker):
    print '* Error: Package Maker does not appear to be installed in its default\n' \
      'location of:\n', args.package_maker, '\n'
    fail = True

  # Is what we are trying to distribute available?
  if args.packages_dir:
    args.packages_dir = args.packages_dir.rstrip(os.path.sep)
    if not os.path.exists(args.packages_dir):
      print '* Error: path provided:', args.packages_dir, 'not found'
      fail = True
  else:
    print '* Error: you need to supply a --packages-dir argument pointing\n' \
      'to where you installed everything to (--packages-dir /opt/moose)\n'
    fail = True

  if fail:
    print '\nPlease solve for the failures identified and re-run this script'
    sys.exit(1)
  return args

def parseArguments(args=None):
  parser = argparse.ArgumentParser(description='Create Redistributable Package')
  parser.add_argument('-p', '--packages-dir', help='Directory where you installed everything to (/opt/moose)')
  parser.add_argument('--package-type', help='Specify type of package to build. Valid values: deb rpm pkg')
  parser.add_argument('--force', action='store_const', const=True, default=False, help='Force building package even if script could not determine OS release version')
  parser.add_argument('--meta-dir', default=os.path.join(os.environ['HOME'], 'package_versioning'), help='Absolute path location to store versioning information')
  parser.add_argument('--sign', help='Sign the package (Macintosh Only) with the specified key')
  parser.add_argument('-k', '--keep-temporary-files', action='store_const', const=True, default=False, help='Keep temporary directory after package is created (default False')
  return verifyArgs(parser.parse_args(args))


### Base Name (name that preceeds all system and version information
#   when determining the name of the redistributable
# (_base_name_system-release-version_x86_64.deb)
_base_name = 'moose-environment'

### PackageMaker location (default on OS X)
_package_maker = '/Applications/PackageMaker.app/Contents/MacOS/PackageMaker'

### List of OS X versions that need a symbolic link to openmp
_need_symbolic_link = ['']

### A dictionary of class pointers corresponding to OS type
_pathetic_dict = { RPM : ['FEDORA', 'SUSE', 'CENTOS', 'RHEL'],
                   DEB : ['UBUNTU', 'MINT', 'DEBIAN', 'KUBUNTU'],
                   PKG : ['DARWIN']}

### Conversion of OS X version to release name
_mac_version_to_name = {'10.9'  : 'mavericks',
                        '10.10' : 'yosemite',
                        '10.11' : 'elcapitan',
                        '10.12' : 'sierra',
                        '10.13' : 'highsierra'}

if __name__ == '__main__':
  args = parseArguments()
  package = args.package_type(args)
  if package.prepare_area():
    if package.create_tarball():
      if package.create_redistributable():
        print 'Finished successfully. Removing temporary files..'
  if not args.keep_temporary_files:
    package.clean_up()
