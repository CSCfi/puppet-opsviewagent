#!/usr/bin/python3

import argparse
import subprocess

import MySQLdb

NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3

query = "select instances.UUID,ports.mac_address,json_unquote(json_extract(agents.configurations,'$.tunneling_ip')) as ip,networksegments.segmentation_id from nova.instances inner join neutron.ports on instances.UUID = ports.device_id inner join neutron.agents on instances.host = agents.host inner join neutron.networksegments on ports.network_id = networksegments.network_id where instances.deleted_at is NULL and networksegments.network_type = 'vxlan'"

fdb_command = """bridge fdb show | grep vxlan | grep dst | awk '{ print $1" "substr($3,7)" "$5 }'"""

excluded_macs = [
    "00:00:00:00:00:00",
]

def get_data_from_db(db_data, db, user, password):
    try:
        conn = MySQLdb.connect(
            host=db,
            user=user,
            password=password
        )
        cur = conn.cursor()
        cur.execute(query)
        for row in cur:
            key=row[1] + "_" + str(row[3])
            assert key not in db_data.keys()
            db_data[key] = {}
            db_data[key]['instance_uuid'] = row[0]
            db_data[key]['mac_address'] = row[1]
            db_data[key]['ip_address'] = row[2]
            db_data[key]['vxlan_id'] = str(row[3])
    except MySQLdb.Error as e:
        print(f"Error connecting to MariaDB: {e}")
        return NAGIOS_STATE_CRITICAL
    finally:
        if conn:
            conn.close()
    return NAGIOS_STATE_OK

def get_data_from_fdb(fdb_data):
    try:
        output = subprocess.run(fdb_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        for line in output.stdout.split('\n')[:-1]:
            pieces = line.split(' ')
            if pieces[0] not in excluded_macs:
                key = pieces[0] + "_" + pieces[1]
                assert key not in fdb_data.keys()
                fdb_data[key] = {}
                fdb_data[key]['mac_address'] = pieces[0]
                fdb_data[key]['vxlan_id'] = pieces[1]
                fdb_data[key]['ip_address'] = pieces[2]
    except subprocess.CalledProcessError as e:
        print("Failed to run command:", e)
        return NAGIOS_STATE_CRITICAL
    return NAGIOS_STATE_OK

def main():
    parser = argparse.ArgumentParser(description='Compares the data on how to reach a virtual machine in a vxlan. It compares the data in the database with the data in the local forwarding database (fdb).')
    parser.add_argument('-d','--db', help='FQDN or IP address of the database', required=True)
    parser.add_argument('-u','--user', help='User of the database', required=True)
    parser.add_argument('-p','--password', help='Password of the database user', required=True)
    args = vars(parser.parse_args())
    exit_code = NAGIOS_STATE_OK
    db_data = {}
    exit_code = get_data_from_db(db_data, args['db'], args['user'], args['password'])
    if exit_code == NAGIOS_STATE_OK:
        fdb_data = {}
        exit_code = get_data_from_fdb(fdb_data)
        if exit_code == NAGIOS_STATE_OK:
            for key in set(db_data.keys()).intersection(set(fdb_data.keys())):
                assert db_data[key]["mac_address"] == fdb_data[key]["mac_address"]
                assert db_data[key]["vxlan_id"] == fdb_data[key]["vxlan_id"]
                if db_data[key]['ip_address'] != fdb_data[key]['ip_address']:
                    print("vm " + db_data[key]["instance_uuid"] + " - fdb entry for mac address " + db_data[key]['mac_address'] + " in vxlan " + db_data[key]['vxlan_id'] + " should point to hypervisor at address " + db_data[key]["ip_address"] + " but it is instead pointing to hypervisor at address " + fdb_data[key]["ip_address"])
                    exit_code = NAGIOS_STATE_CRITICAL
    if exit_code == NAGIOS_STATE_OK:
        print("all fdb entries match the information in the database")
    exit(exit_code)

if __name__ == '__main__':
  main()
