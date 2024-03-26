class opsviewagent::params {
  if $facts['os']['family'] == "RedHat" {
    $repo_url = "http://downloads.opsview.com/opsview-core/latest/yum/centos/${facts['os']['release']['major']}Server/\$basearch"
    case $facts['os']['release']['major'] {
        '7','8','9': {
          $firewall_manager = 'firewalld'
        }
        default: {
          fail('Your OS is not supported by the opsview module.')
        }
    }
  }
  else {
    fail('Your operating system is not supported by the opsview module')
  }
}
