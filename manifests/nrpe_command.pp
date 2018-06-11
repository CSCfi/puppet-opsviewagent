define opsviewagent::nrpe_command(
  $script_name,
  $script_arguments,
  $use_sudo = false,
) {
  File[$name] ~> Service['nrpe-daemon-service']

  # script is defined with absolute path
  if $script_name =~ /^\/.*/ {
    $command = "${script_name}"
  } else {
    $command = "${opsviewagent::nrpe_local_script_path}/${script_name}"
  }

  if $use_sudo == false {
    file { $name:
      path    => "${opsviewagent::nrpe_local_configs_path}/${name}.cfg",
      content => "command[${name}]=${command} ${script_arguments}\n",
      owner   => "${opsviewagent::nagios_user}",
      group   => "${opsviewagent::nagios_user}",
      mode    => '0600',
    }
  }
  else {
    file { $name:
      path    => "${opsviewagent::nrpe_local_configs_path}/${name}.cfg",
      content => "command[${name}]=sudo ${command} ${script_arguments}\n",
      owner   => "${opsviewagent::nagios_user}",
      group   => "${opsviewagent::nagios_user}",
      mode    => '0600',
    }

    sudo::conf { $name:
      content  => "Defaults !requiretty\n${opsviewagent::nagios_user} ALL=(ALL) NOPASSWD: ${command}\n",
    }
  }
}
