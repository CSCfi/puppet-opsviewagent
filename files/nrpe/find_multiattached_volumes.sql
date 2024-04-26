# Prints non-multiattach instances from nova.block_device_mappings table that have multiple mappings
SELECT my_uuids
FROM
(
  SELECT
    volume_id AS my_uuids,
    count(*) AS VOLUME_COUNT
  FROM
    nova.block_device_mapping
  WHERE
    deleted_at IS NULL AND
    source_type="volume" AND
    JSON_EXTRACT(connection_info,'$.multiattach') IS not True
  GROUP BY
    volume_id
  HAVING
    VOLUME_COUNT > 1
)
AS T

