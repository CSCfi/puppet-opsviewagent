define opsviewagent::nrpe_script(
  $script_source,
) {
  file { $name:
    path    => "${opsviewagent::nrpe_local_script_path}/${name}",
    source  => $script_source,
    owner   => 'nagios',
    group   => 'nagios',
    mode    => 550,
  }
}
