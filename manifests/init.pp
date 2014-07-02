# == Class: opsviewagent
#
# Full description of class opsviewagent here.
#
# === Parameters
#
# Document parameters here.
#
# [*sample_parameter*]
#   Explanation of what this parameter affects and what it defaults to.
#   e.g. "Specify one or more upstream ntp servers as an array."
#
# === Variables
#
# Here you should define a list of variables that this module would require.
#
# [*sample_variable*]
#   Explanation of how this variable affects the funtion of this class and if it
#   has a default. e.g. "The parameter enc_ntp_servers must be set by the
#   External Node Classifier as a comma separated list of hostnames." (Note,
#   global variables should not be used in preference to class parameters  as of
#   Puppet 2.6.)
#
# === Examples
#
#  class { opsviewagent:
#    servers => [ 'pool.ntp.org', 'ntp.local.company.com' ]
#  }
#
# === Authors
#
# Author Name <author@domain.com>
#
# === Copyright
#
# Copyright 2014 Your name here, unless otherwise noted.
#
class opsviewagent (
  $allowed_hosts,
  $nrpe_allowed_net,
  $nrpe_port = '5666',
  $nrpe_local_script_path = '/usr/local/nagios/libexec/nrpe_local',
  $nrpe_local_configs_path = '/usr/local/nagios/etc/nrpe_local',
  $command_timeout = 50,
){
  $hosts = join( $allowed_hosts, ',' )

  Yumrepo['opsview'] ~> Package['opsview-agent']
  Package['opsview-agent'] -> File['nrpe.cfg']
  Package['opsview-agent'] -> Service['opsview-agent']
  File<||> -> Service['opsview-agent']
  File['nrpe.cfg'] ~> Service['opsview-agent']

  firewall { '200 open nrpe port':
    port    => $nrpe_port,
    proto   => 'tcp',
    state   => 'NEW',
    action  => 'accept',
    source  => $nrpe_allowed_net,
  }

  yumrepo { 'opsview':
    baseurl   => 'http://downloads.opsview.com/opsview-core/latest/yum/centos/6Server/$basearch',
    enabled   => '1',
    protect   => '0',
    gpgcheck  => '0',
  }

  package { 'opsview-agent':
    ensure  => installed,
  }

  service { 'opsview-agent':
    ensure  => running,
    enable  => true,
  }

  file { 'nrpe.cfg':
    path    => '/usr/local/nagios/etc/nrpe.cfg', 
    content => template("opsviewagent/nrpe.cfg.erb"),
    mode    => 644,
    owner   => 'root',
    group   => 'root',
  }

  file { 'nrpe-scripts':
    path    => $nrpe_local_script_path,
    source  => 'puppet:///modules/opsviewagent/nrpe/',
    recurse => true,
    purge   => true,
    mode    => 550,
    owner   => 'nagios',
    group   => 'nagios',
  }
}
