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
  $manage_firewall = true,
  $nagios_user = 'nagios',
  $nagios_public_ssh_key = undef,
  $manage_yum_repos = true,
){
  include opsviewagent::params

  $hosts = join( $allowed_hosts, ',' )

  if $manage_yum_repos {
    Yumrepo['opsview'] ~> Package['opsview-agent']
  }

  Package['opsview-agent'] -> File['nrpe.cfg']
  Package['opsview-agent'] -> File['nrpe-configs']
  Package['opsview-agent'] -> File['nrpe-scripts']
  Package['opsview-agent'] -> Service['opsview-agent']
  Package['opsview-agent'] -> Opsviewagent::Nrpe_command<||>
  File['nrpe-scripts'] -> Service['opsview-agent']
  File['nrpe-configs'] -> Service['opsview-agent']
  File['nrpe.cfg'] ~> Service['opsview-agent']

  if $manage_firewall {
    case $::opsviewagent::params::firewall_manager {
      'iptables': {
        firewall { '200 open nrpe port':
          port   => $nrpe_port,
          proto  => 'tcp',
          state  => 'NEW',
          action => 'accept',
          source => $nrpe_allowed_net,
        }
      }
      'firewalld': {
        firewalld::service { 'gearman':
          ports => [
          { port     => $nrpe_port,
            protocol => 'tcp' },
          ]
        }
      }
      default: {
        fail('Your OS is not supported by the opsview module.')
      }
    }
  }

  user { $nagios_user:
    ensure     => present,
    name       => $nagios_user,
    home       => "/var/log/${nagios_user}",
    managehome => true,
    comment    => 'Monitoring user',
  }

  if $nagios_public_ssh_key {
    ssh_authorized_key { "${nagios_user}@taito-service01.csc.fi":
      user => $nagios_user,
      type => 'ssh-rsa',
      key  => $nagios_public_ssh_key,
    }
  }

  if $manage_yum_repos {
    yumrepo { 'opsview':
      baseurl  => $::opsviewagent::params::repo_url,
      enabled  => '1',
      protect  => '0',
      gpgcheck => '0',
    }
  }

  package { 'opsview-agent':
    ensure  => installed,
    require => User['nagios'],
  }

  package { 'gawk':
    ensure  => installed,
  }

  package { 'bc':
    ensure  => installed,
  }

  service { 'opsview-agent':
    ensure => running,
    enable => true,
  }

  file { 'nrpe.cfg':
    path    => '/usr/local/nagios/etc/nrpe.cfg',
    content => template('opsviewagent/nrpe.cfg.erb'),
    mode    => '0644',
    owner   => 'root',
    group   => 'root',
  }

  file { 'nrpe-configs':
    ensure  => directory,
    path    => $nrpe_local_configs_path,
    recurse => true,
    purge   => true,
    mode    => '0550',
    owner   => 'nagios',
    group   => 'nagios',
  }

  file { 'nrpe-scripts':
    path    => $nrpe_local_script_path,
    source  => 'puppet:///modules/opsviewagent/nrpe/',
    recurse => true,
    purge   => true,
    mode    => '0550',
    owner   => 'nagios',
    group   => 'nagios',
  }

}
