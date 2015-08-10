class opsviewagent::params {
  case $::operatingsystem {
    'CentOS': {
      $repo_url = "http://downloads.opsview.com/opsview-core/latest/yum/centos/${::operatingsystemmajrelease}Server/\$basearch"
      case $::operatingsystemmajrelease {
        '7': {
          $firewall_manager = 'firewalld'
        }
        '6': {
          $firewall_manager = 'iptables'
        }
        default: {
          fail('Your OS is not supported by the opsview module.')
        }
      }
    }
    default: {
      fail('Your operating system is not supported by the opsview module')
    }
  }
}
