class opsviewagent::params {
  case $::operatingsystem {
    'CentOS': {
      $repo_url = "http://downloads.opsview.com/opsview-core/latest/yum/centos/${::operatingsystemmajrelease}Server/\$basearch"
    }
    default: {
      fail('Your operating system is not supported by the opsview module')
    }
  }
}
