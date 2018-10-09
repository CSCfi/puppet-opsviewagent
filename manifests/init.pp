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
  $nrpe_local_configs_path = '/etc/nrpe.d',
  $nrpe_cfg_override_configs_path = '/etc/nrpe.d/override.cfg',
  $command_timeout = 50,
  $manage_firewall = true,
  $nagios_user = 'nrpe',
  $nagios_public_ssh_key = undef,
  $manage_yum_repos = false,
  $package_name = 'nrpe',
  $service_name = 'nrpe',
){
  include opsviewagent::params

  $hosts = join( $allowed_hosts, ',' )

  if $manage_yum_repos {
    Yumrepo['opsview'] ~> Package['nrpe-daemon']
  }

  Package['nrpe-daemon'] -> File['nrpe.cfg']
  Package['nrpe-daemon'] -> File['nrpe-configs']
  Package['nrpe-daemon'] -> File['nrpe-scripts']
  Package['nrpe-daemon'] -> Service['nrpe-daemon-service']
  Package['nrpe-daemon'] -> Opsviewagent::Nrpe_command<||>
  User[$nagios_user] -> Package['nrpe-daemon']
  File['opsview-nagios-dir'] -> File['opsview-libexec-dir']
  File['opsview-libexec-dir'] -> File['nrpe-scripts']
  File['nrpe-unitfile'] ~> Service['nrpe-daemon-service']
  File['nrpe-scripts'] ~> Service['nrpe-daemon-service']
  File['nrpe-configs'] ~> Service['nrpe-daemon-service']
  File['nrpe.cfg'] ~> Service['nrpe-daemon-service']

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
      user    => $nagios_user,
      type    => 'ssh-rsa',
      key     => $nagios_public_ssh_key,
      require => User[$nagios_user],
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

  package { 'nrpe-daemon':
    name    => $package_name,
    ensure  => installed,
  }
  if $package_name == 'nrpe' {
    package { 'opsview-agent-removal':
      name   => 'opsview-agent',
      ensure => absent,
      before => User[$nagios_user],
    }
  }

  package { 'gawk':
    ensure  => installed,
  }

  package { 'bc':
    ensure  => installed,
  }

  package { ['nagios-plugins-disk', 'nagios-plugins-ntp', 'nagios-plugins-procs', 'nagios-plugins-load', 'nagios-plugins-swap', 'nagios-plugins-perl', 'nagios-plugins-http']:
    ensure  => installed,
    require => Package['nrpe-daemon'],
  }

  service { 'nrpe-daemon-service':
    name    => $service_name,
    ensure  => running,
    enable  => true,
  }

  file { 'nrpe.cfg':
    path    => $nrpe_cfg_override_configs_path,
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
    owner   => $nagios_user,
    group   => $nagios_user,
  }

  file { 'opsview-nagios-dir':
    ensure  => directory,
    path    => '/usr/local/nagios',
    mode    => '0550',
    owner   => $nagios_user,
    group   => $nagios_user,
  }
  file { 'opsview-libexec-dir':
    ensure  => directory,
    path    => '/usr/local/nagios/libexec',
    mode    => '0550',
    owner   => $nagios_user,
    group   => $nagios_user,
  }


  file { 'nrpe-scripts':
    ensure  => directory,
    path    => $nrpe_local_script_path,
    source  => 'puppet:///modules/opsviewagent/nrpe/',
    recurse => true,
    purge   => true,
    mode    => '0550',
    owner   => $nagios_user,
    group   => $nagios_user,
  }

  file { 'nrpe-unitfile':
    ensure  => file,
    path    => '/usr/lib/systemd/system/nrpe.service',
    owner   => 'root',
    group   => 'root',
    mode    => '0644',
    content => template('opsviewagent/nrpe.service.erb'),
  }

  exec { 'systemctl daemon-reload on nrpe unitfile change':
    command     => 'systemctl daemon-reload',
    refreshonly => true,
    logoutput   => on_failure,
    subscribe   => File['nrpe-unitfile'],
    notify      => Service['nrpe-daemon-service'],
  }

}
