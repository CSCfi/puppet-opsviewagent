# Prints instances from nova.pci_devices table that have a different amount of pci devices than their flavors
# Assumes that column value for flavors with pci_aliases are colon separated like M10:1 or P100:4
SELECT my_uuids
FROM
(
  SELECT 
    pcid.instance_uuid as my_uuids,
    count(pcid.instance_uuid) as actual_gpus,
    SUBSTRING_INDEX(flex.value, ':', -1) as flavor_gpus
  FROM 
    nova.pci_devices pcid, 
    nova.instances inst,
    nova_api.flavor_extra_specs flex
  WHERE 
    pcid.status = "allocated" AND 
    inst.uuid = pcid.instance_uuid AND
    inst.instance_type_id = flex.flavor_id AND
    flex.`key` LIKE "%alias"
  GROUP BY 
    pcid.instance_uuid
  HAVING 
    actual_gpus != flavor_gpus
) 
AS T
