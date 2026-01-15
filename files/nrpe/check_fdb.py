#!/usr/bin/python3

"""
check_fdb.py

The script compares the data about reachability of virtual machines in vxlan
networks. Specifically, the script compares the data from the remote database
with the data contained in the local forwarding database (fdb).
If the data matches, the script exits with return code 0.
If there are discrepancies, the script exits with return code 1.
"""

import argparse
import subprocess
import sys

import MySQLdb

NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3

QUERY = ("SELECT "
         "instances.UUID,"
         "ports.mac_address,"
         "json_unquote(json_extract(agents.configurations,'$.tunneling_ip')) as ip,"
         "networksegments.segmentation_id "
         "FROM "
         "nova.instances "
         "INNER JOIN neutron.ports ON instances.UUID = ports.device_id "
         "INNER JOIN neutron.agents ON instances.host = agents.host "
         "INNER JOIN neutron.networksegments ON ports.network_id = networksegments.network_id "
         "WHERE "
         "instances.deleted_at IS NULL "
         "AND "
         "networksegments.network_type = 'vxlan'")

FDB_COMMAND = """bridge fdb show | grep dst | grep vxlan | awk '{ print $1" "substr($3,7)" "$5 }'"""

EXCLUDED_MACS = [
    "00:00:00:00:00:00",
]

def get_data_from_db(db_data, database, user, password):
    """
    The function retrieves the data about the reachability of the virtual
    machines from the database and fills the dictionary db_data with it.
    """
    try:
        conn = MySQLdb.connect(
            host=database,
            user=user,
            password=password
        )
        cur = conn.cursor()
        cur.execute(QUERY)
        for row in cur:
            # a mac address is not guaranteed to be unique, so we create a key
            # by combining it with the corresponding vxlan id
            key=row[1] + "_" + str(row[3])
            assert key not in db_data.keys()
            db_data[key] = {}
            db_data[key]['instance_uuid'] = row[0]
            db_data[key]['mac_address'] = row[1]
            db_data[key]['ip_address'] = row[2]
            db_data[key]['vxlan_id'] = str(row[3])
    except MySQLdb.Error as exception:
        print(f"Error connecting to MariaDB: {exception}")
        return NAGIOS_STATE_CRITICAL
    finally:
        if conn:
            conn.close()
    return NAGIOS_STATE_OK

def get_data_from_fdb(fdb_data):
    """
    The function retrieves the data about the reachability of the virtual
    machines from the local fdb and fills the dictionary fdb_data with it.
    """
    try:
        output = subprocess.run(
            FDB_COMMAND,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False
        )
        for line in output.stdout.split('\n')[:-1]:
            pieces = line.split(' ')
            if pieces[0] not in EXCLUDED_MACS:
                # a mac address is not guaranteed to be unique, so we create a
                # key by combining it with the corresponding vxlan id
                key = pieces[0] + "_" + pieces[1]
                assert key not in fdb_data.keys()
                fdb_data[key] = {}
                fdb_data[key]['mac_address'] = pieces[0]
                fdb_data[key]['vxlan_id'] = pieces[1]
                fdb_data[key]['ip_address'] = pieces[2]
    except subprocess.CalledProcessError as exception:
        print("Failed to run command:", exception)
        return NAGIOS_STATE_CRITICAL
    return NAGIOS_STATE_OK

def main():
    """
    The script:
    - retrieves the data from the database
    - retrieves the data from the local fdb
    - iterates over the mac addresses that appear in both datasets
    - if some discrepancies between the data about the same virtual machine is
      found, the script prints it
    """
    parser = argparse.ArgumentParser(
        description=("Compares the data on how to reach a virtual machine in "
                     "a vxlan. It compares the data in the database with the "
                     "data in the local forwarding database (fdb).")
        )
    parser.add_argument('-d','--database', help='FQDN or IP address of the database', required=True)
    parser.add_argument('-u','--user', help='User of the database', required=True)
    parser.add_argument('-p','--password', help='Password of the database user', required=True)
    args = vars(parser.parse_args())
    exit_code = NAGIOS_STATE_OK
    db_data = {}
    exit_code = get_data_from_db(db_data, args['database'], args['user'], args['password'])
    if exit_code == NAGIOS_STATE_OK:
        fdb_data = {}
        exit_code = get_data_from_fdb(fdb_data)
        if exit_code == NAGIOS_STATE_OK:
            for key in set(db_data.keys()).intersection(set(fdb_data.keys())):
                assert db_data[key]["mac_address"] == fdb_data[key]["mac_address"]
                assert db_data[key]["vxlan_id"] == fdb_data[key]["vxlan_id"]
                if db_data[key]['ip_address'] != fdb_data[key]['ip_address']:
                    print("vm " + db_data[key]["instance_uuid"] + " - " +
                          "fdb entry for mac address " + db_data[key]['mac_address'] + " " +
                          "in vxlan " + db_data[key]['vxlan_id'] + " " +
                          "should point to " +
                          "hypervisor at address " + db_data[key]["ip_address"] + " " +
                          "but it is instead pointing to " +
                          "hypervisor at address " + fdb_data[key]["ip_address"])
                    exit_code = NAGIOS_STATE_CRITICAL
    if exit_code == NAGIOS_STATE_OK:
        print("all fdb entries match the information in the database")
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
