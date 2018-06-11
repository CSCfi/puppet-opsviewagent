[![Build Status](https://travis-ci.org/CSCfi/puppet-opsviewagent.svg?branch=master)](https://travis-ci.org/CSCfi/puppet-opsviewagent)

opsviewagent
============

This is the opsviewagent module.

**It currently defaults to installing NRPE.**

It no longer works great with opsview-agent (especially the nrpe.cfg has some now nrpe hard coded paths).

To resolve conflicts between the packages when changing from opsview-agent to nrpe then before nrpe is installed the role will ensure opsview-agent is absent.

License
-------


Contact
-------


Support
-------

Please log tickets and issues here on Github
