define opsviewagent::nrpe_command(
  $script_name,
  $script_arguments,
  $use_sudo = false,
) {
  File[$name] ~> Service['opsview-agent']

  if $sudo == false {
    file { $name:
      path    => "${opsviewagent::nrpe_local_configs_path}/${name}.cfg",
      content => "command[${name}]=${opsviewagent::nrpe_local_script_path}/${script_name} ${script_arguments}\n",
      owner   => 'nagios',
      group   => 'nagios',
      mode    => 600,
    }
  }
  else {
    file { $name:
      path    => "${opsviewagent::nrpe_local_configs_path}/${name}.cfg",
      content => "command[${name}]=sudo ${opsviewagent::nrpe_local_script_path}/${script_name} ${script_arguments}\n",
      owner   => 'nagios',
      group   => 'nagios',
      mode    => 600,
    } 

  sudo::conf { '$name':
      content  => "nagios ALL=(ALL) NOPASSWD: ${opsviewagent::nrpe_local_script_path}/${script_name}",
    }
  }
}
