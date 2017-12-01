#
# spec file for package 
#
# Copyright (c) 2013 SUSE LINUX Products GmbH, Nuernberg, Germany.
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via http://bugs.opensuse.org/
#

Name: moose-environment
Version: 1.1
Release: <VERSION>%{?dist}
License: None
Summary: Compilers neccessary to utilize the MOOSE Framework
Url: http://mooseframework.org
Group: Development/Libraries
Source: %{name}.tar.gz
Requires: gcc gcc-c++ make freeglut-devel m4 blas-devel lapack-devel <REQUIREMENTS>
BuildRoot: %{_tmppath}/%{name}-build
AutoReqProv: no

# Prevent debug package from being created
%define debug_package %{nil}
%define __strip /bin/true

# Disable debug symbol stripping
%define __spec_install_port /usr/lib/rpm/brp-compress

# Disable binary stripping
%define __os_install_post %{nil}

# Prevent check-buildroot from running. We do not need it.
%define __arch_install_post /usr/lib/rpm/check-rpaths

%description
This package contains the neccessary libraries/binaries to utilize the MOOSE framework and assocaited applications.

%prep
%setup -q -n <PACKAGES_BASENAME>

%build


%install
export QA_SKIP_RPATHS=true
mkdir -p %{buildroot}/<PACKAGES_BASENAME>
mv -f <PACKAGES_PARENT> %{buildroot}/<PACKAGES_BASENAME>/

%post
echo -e '\n\tAdd the following lines to your ~/.bashrc file to source the MOOSE compiler stack:\n\n\n## Uncomment the following line to enable pretty prompt:\n#export MOOSE_PROMPT=true\n\n## Uncomment the following line to enable autojump:\n#export MOOSE_JUMP=true\n\n## Source the MOOSE profile if moose_profile exists:\nif [ -f <PACKAGES_DIR>/environments/moose_profile ]; then\n  . <PACKAGES_DIR>/environments/moose_profile\nfi'


%postun

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root)
<PACKAGES_DIR>

%changelog
