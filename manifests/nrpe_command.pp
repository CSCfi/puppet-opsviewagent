define opsviewagent::nrpe_command(
  $script_name,
  $script_arguments,
) {
  File[$name] ~> Service['opsview-agent']

  file { $name:
    path    => "${opsviewagent::nrpe_local_configs_path}/${name}.cfg",
    content => "command[${name}]=${opsviewagent::nrpe_local_script_path}/${script_name} ${script_arguments}\n",
    owner   => 'nagios',
    group   => 'nagios',
    mode    => 600,
  }
}
