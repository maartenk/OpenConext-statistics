"""
Will drop and re-create all measurements and continuous queries and backfill the measurements
from the main login measurement
"""
import logging
import os
import time

from influxdb import InfluxDBClient

VALID_PERIODS = ["minute", "hour", "day", "week", "month", "quarter", "year"]
VALID_GROUP_BY = ["minute", "hour", "day", "week"]

logger = logging.getLogger()


def append_measurement(l, period, postfix=""):
    l.append(f"sp_idp_users_{period}{postfix}")
    l.append(f"sp_idp_pa_users_{period}{postfix}")
    l.append(f"sp_idp_ta_users_{period}{postfix}")
    l.append(f"idp_users_{period}{postfix}")
    l.append(f"idp_pa_users_{period}{postfix}")
    l.append(f"idp_ta_users_{period}{postfix}")
    l.append(f"sp_users_{period}{postfix}")
    l.append(f"sp_pa_users_{period}{postfix}")
    l.append(f"sp_tp_users_{period}{postfix}")
    l.append(f"total_users_{period}{postfix}")
    l.append(f"total_pa_users_{period}{postfix}")
    l.append(f"total_ta_users_{period}{postfix}")


def get_measurements():
    measurements = []
    for period in VALID_PERIODS:
        append_measurement(measurements, period)
        if period != "minute":
            append_measurement(measurements, period, postfix="_unique")
    return measurements


def create_continuous_query(db, db_name, duration, period, is_unique, include_total, measurement_name, parent_name,
                            group_by=[], state=None):
    q = "SELECT "
    q += "count(distinct(\"user_id\")) as distinct_count_user_id " \
        if is_unique else "sum(\"count_user_id\") as count_user_id "
    q += ", count(\"user_id\") as count_user_id " if is_unique and include_total else ""
    q += f"INTO \"{measurement_name}\" FROM \"{parent_name}\" "
    state_value = "prodaccepted" if state == "pa" else "testaccepted" if state == "ta" else None
    q += f" WHERE state = '{state_value}' " if state_value else ""
    if period in VALID_GROUP_BY:
        group_by += ["year", "month", "quarter", f"time({'1w,4d' if period == 'week' else duration })"]

    if period in ["month", "quarter", "year"]:
        group_by.append("time(15250w)")
        group_by.append("year")
        if period in ["month", "quarter"]:
            group_by.append(period)

    if len(group_by) > 0:
        q += f"GROUP BY {', '.join(group_by)} "

    # See https://community.influxdata.com/t/dependent-continuous-queries-at-multiple-resolutions/638/3
    every = "1d"
    if period in ["minute", "hour"]:
        every = "5m" if period == "minute" else "1h"
    # See https://docs.influxdata.com/influxdb/v1.6/query_language/continuous_queries/#examples-of-advanced-syntax
    _for = ""
    if period in VALID_GROUP_BY:
        if period == "minute":
            _for = "FOR 10m"
        else:
            _for = "FOR 2" + period[:1]

    cq = f"CREATE CONTINUOUS QUERY \"{measurement_name}_cq\" " \
         f"ON \"{db_name}\" RESAMPLE EVERY {every} {_for} BEGIN {q} END"
    logger.info(f"{cq}")
    db.query(cq)

    # backfill the history
    logger.info(f"{q}")
    db.query(q)

    if not os.environ.get("TEST"):
        # need to give influx some time to index
        time.sleep(10 * 60 if "minute" in measurement_name else 5 * 60 if "hour" in measurement_name else 60)


def backfill_login_measurements(config, db: InfluxDBClient):
    db_name = config.database.name
    log_source = config.log.measurement

    sp = config.log.sp_id
    idp = config.log.idp_id

    databases = list(map(lambda p: p["name"], db.get_list_database()))

    if db_name not in databases:
        # we assume a test is running and we don't proceed with back filling
        return

    for measurement in get_measurements():
        db.drop_measurement(measurement)

    continuous_queries = list(map(lambda x: x["name"], db.query("show continuous queries").get_points()))
    for cq in continuous_queries:
        db.query(f"drop continuous query {cq} on {db_name}")

    # First create all the unique count queries that have to run against the log_source
    for p in VALID_PERIODS:
        for state in ["pa", "ta", None]:
            duration = "1" + p[:1]
            include_total = p == "minute"
            unique_postfix = "_unique" if p != "minute" else ""
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=p, is_unique=True,
                                    include_total=include_total,
                                    measurement_name=f"sp_idp_{state}_users_{p}{unique_postfix}"
                                    if state else f"sp_idp_users_{p}{unique_postfix}",
                                    parent_name=log_source,
                                    group_by=[sp, idp],
                                    state=state)
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=p, is_unique=True,
                                    include_total=include_total,
                                    measurement_name=f"idp_{state}_users_{p}{unique_postfix}"
                                    if state else f"idp_users_{p}{unique_postfix}",
                                    parent_name=log_source,
                                    group_by=[idp],
                                    state=state)
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=p, is_unique=True,
                                    include_total=include_total,
                                    measurement_name=f"sp_{state}_users_{p}{unique_postfix}"
                                    if state else f"sp_users_{p}{unique_postfix}",
                                    parent_name=log_source,
                                    group_by=[sp],
                                    state=state)
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=p, is_unique=True,
                                    include_total=include_total,
                                    measurement_name=f"total_{state}_users_{p}{unique_postfix}"
                                    if state else f"total_users_{p}{unique_postfix}",
                                    parent_name=log_source,
                                    group_by=[],
                                    state=state)

    for d, p in (("hour", "minute"), ("day", "hour"), ("week", "day"), ("month", "week"), ("quarter", "week"),
                 ("year", "week")):
        duration = "1" + d[:1]
        for state in ["pa", "ta", None]:
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=d, is_unique=False,
                                    include_total=False,
                                    measurement_name=f"sp_idp_{state}_users_{d}"
                                    if state else f"sp_idp_users_{d}",
                                    parent_name=f"sp_idp_{state}_users_{p}"
                                    if state else f"sp_idp_users_{p}",
                                    group_by=[sp, idp])
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=d, is_unique=False,
                                    include_total=False,
                                    measurement_name=f"idp_{state}_users_{d}"
                                    if state else f"idp_users_{d}",
                                    parent_name=f"idp_{state}_users_{p}"
                                    if state else f"idp_users_{p}",
                                    group_by=[idp])
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=d, is_unique=False,
                                    include_total=False,
                                    measurement_name=f"sp_{state}_users_{d}"
                                    if state else f"sp_users_{d}",
                                    parent_name=f"sp_{state}_users_{p}"
                                    if state else f"sp_users_{p}",
                                    group_by=[sp])
            create_continuous_query(db=db, db_name=db_name, duration=duration, period=d, is_unique=False,
                                    include_total=False,
                                    measurement_name=f"total_{state}_users_{d}"
                                    if state else f"total_users_{d}",
                                    parent_name=f"total_{state}_users_{p}"
                                    if state else f"total_users_{p}",
                                    group_by=[])
