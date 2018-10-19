#!/bin/bash
# Remove previous <PACKAGES_DIR>, we have no reason to save it anymore.
# If someone is installing stuff into our directory, their loss.
if [ -d <PACKAGES_DIR> ]; then
  rm -rf <PACKAGES_DIR>
  mkdir -p <PACKAGES_DIR>
else
  mkdir -p <PACKAGES_DIR>
fi

# I do not like extracting tarballs to '/', but in this case
# it is the correct thing to do now, since the payload.tar.gz
# file is created via script based on --package-dir argument
# meaning: the intended target could be anywhere
tar -xf /private/tmp/MOOSE_installer-tmp/payload.tar.gz -C /
chown -R root:wheel <PACKAGES_DIR>
