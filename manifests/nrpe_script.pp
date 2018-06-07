define opsviewagent::nrpe_script(
  $script_source,
) {
  File[$name] ~> Service['opsview-agent']

  file { $name:
    path    => "${opsviewagent::nrpe_local_script_path}/${name}",
    source  => $script_source,
    owner   => "${opsviewagent::nagios_user}",
    group   => "${opsviewagent::nagios_user}",
    mode    => 550,
  }
}
