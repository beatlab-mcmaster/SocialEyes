import os

import clickhouse_driver

CLICKHOUSE_URL = os.getenv("CLICKHOUSE_DB")


class NoDBConnectionException(Exception):
    pass


def get_clickhouse_client(clickhouse_url=CLICKHOUSE_URL):
    if not clickhouse_url:
        return
    client = clickhouse_driver.Client.from_url(clickhouse_url)
    if has_clickhouse_connection(client):
        return client


def has_clickhouse_connection(clickhouse_client):
    try:
        clickhouse_client.execute("SELECT * from recording_gazepoints LIMIT 1")
    except NoDBConnectionException:
        return False
    return True


def get_gaze_data(
    recording, start_epoch_ns: int = None, end_epoch_ns: int = None, limit: int = None
):
    client = get_clickhouse_client()
    if not client:
        return
    query = """
        SELECT
            epoch_ns, undistorted_x, undistorted_y
        FROM
            recording_gazepoints
        WHERE
            recording_id = %(recording_id)s
    """
    params = {"recording_id": str(recording.id)}
    if start_epoch_ns:
        query += " AND epoch_ns >= %(start_epoch_ns)d"
        params.update({"start_epoch_ns": start_epoch_ns})
    if end_epoch_ns:
        query += " AND epoch_ns < %(end_epoch_ns)d"
        params.update({"end_epoch_ns": end_epoch_ns})
    if limit:
        query += "LIMIT :limit"
        params.update({"limit": limit})

    for row in client.execute_iter(query, params):
        epoch_ns, undist_x, undist_y = row
        yield epoch_ns, undist_x, undist_y


def get_worn_data(
    recording, start_epoch_ns: int = None, end_epoch_ns: int = None, limit: int = None
):
    client = get_clickhouse_client()
    if not client:
        return
    query = """
        SELECT
            epoch_ns, worn
        FROM
            recording_gazepoints
        WHERE
            recording_id = %(recording_id)s
    """
    params = {"recording_id": str(recording.id)}
    if start_epoch_ns:
        query += " AND epoch_ns >= %(start_epoch_ns)d"
        params.update({"start_epoch_ns": start_epoch_ns})
    if end_epoch_ns:
        query += " AND epoch_ns < %(end_epoch_ns)d"
        params.update({"end_epoch_ns": end_epoch_ns})
    if limit:
        query += "LIMIT :limit"
        params.update({"limit": limit})

    for row in client.execute_iter(query, params):
        epoch_ns, worn = row
        yield epoch_ns, worn
