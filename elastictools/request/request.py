def add_getter(getters, getter_name, field_name, additional_level=None):
    if getter_name is None:
        return
    getter = None
    if additional_level is None:
        def getter_(response_body, *args, **kwargs):
            return response_body[field_name]
        getter = getter_
    else:
        def getter_(response_body, *args, **kwargs):
            return response_body[additional_level][field_name]
        getter = getter_
        pass

    if getter_name is not None:
        getters.update({
            getter_name: getter
        })
        pass
    pass


def agg(body):
    getters = {}
    aggs_bodys = {}
    if "aggs" in body:
        aggs_bodys = {key: body["aggs"][key]["body"] for key in body["aggs"]}
        for aggr in body["aggs"]:
            for getter in body["aggs"][aggr]["getters"]:
                getters.update(body["getter_updater"](body["aggs"][aggr]["getters"][getter], aggr, getter))
    getters.update(body["getters"])
    axis = None
    if "axis_maker" in body:
        child_axis = lambda x: {}
        child = None
        if "aggs" in body:
            for child_ in body["aggs"]:
                if "axis" in body["aggs"][child_]:
                    child_axis = body["aggs"][child_]["axis"]
                    child = child_
                    break
        axis = body["axis_maker"](child_axis, child)

    body = {**body["body"], **({"aggs": aggs_bodys} if len(aggs_bodys) > 0 else {})}
    return {"body": body, "getters": getters, **({"axis": axis} if axis is not None else {})}


def bucket_agg(func):
    def decorated_agg(*args, **kwargs):
        return agg(func(*args, **kwargs))
    return decorated_agg


def plain_multi_bucket_getter_updater(getter, key, getter_name):
    def deeper_getter(response_body, *args, **kwargs):
        return [getter(bucket[key], *args, **kwargs) for bucket in response_body["buckets"]]
    return {getter_name: deeper_getter}


def axis_multi_bucket_getter_updater(getter, key, getter_name):
    def deeper_getter(response_body, bucket_id, *args, **kwargs):
        return getter(response_body["buckets"][bucket_id][key], *args, **kwargs)
    return {getter_name: deeper_getter}


def split_multi_bucket_getter_updater_factory(bucket_keys):
    def split_multi_bucket_getter_updater(getter, key, getter_name):
        def inner_fucktory(bucket_key):
            def deeper_getter(response_body, *args, **kwargs):
                b_id = None
                for index, bucket in enumerate(response_body["buckets"]):
                    if bucket["key"] == bucket_key:
                        b_id = index
                        pass
                    pass
                if b_id is None:
                    return None
                return getter(response_body["buckets"][b_id][key], *args, **kwargs)
            return deeper_getter
        return {getter_name + "_" + str(bucket_key): inner_fucktory(bucket_key) for bucket_key in bucket_keys}
    return split_multi_bucket_getter_updater


def multi_bucket_axis_maker(child_axis, key):
    def axis(response_body):
        return {i: child_axis(response_body["buckets"][i][key]) for i in range(len(response_body["buckets"]))}

    def axis2(response_body):
        return {i: {} for i in range(len(response_body["buckets"]))}

    if key is None:
        return axis2
    else:
        return axis


def single_bucket_getter_updater(getter, key, getter_name):
    def deeper_getter(response_body, *args, **kwargs):
        return getter(response_body[key], *args, **kwargs)
    return {getter_name: deeper_getter}


def single_bucket_axis_maker(child_axis, key):
    def axis(response_body):
        return child_axis(response_body[key])

    def axis2(response_body):
        return {}

    if key is None:
        return axis2
    else:
        return axis


def request(query=None, fieldlist=None, sorting=None, **aggs):
    """
    Creates core request body. \n
    :param query: Pure JSON query body. Empty by default. \n
    :param fieldlist: List of fields to write in "_source". Empty by default, which means that all source fields will be included in response hits \n
    :param sorting: Sorting dict, {"filed1": "asc", "field2": "desc} for example \n
    :param aggs: Aggregation objects provided by agg functions \n
    :return: {"body": %plain json request%, "getters": %dictionary of named getters%} \n
    """
    if query is None:
        query = {}
    aggs_bodys = {key: aggs[key]["body"] for key in aggs}
    body = {
        **(
            {
                "query": query
            } if len(query) > 0 else {}
        ),
        **(
            {
                "aggs": aggs_bodys
            } if len(aggs_bodys) > 0 else {}
        ),
        **(
            {
                "_source": fieldlist
            } if fieldlist is not None else {}
        ),
        **(
            {
                "sort":
                {
                    skey:
                    {
                        "order": sorting[skey]
                    } for skey in sorting
                }
            } if sorting is not None else {}
        )
    }

    def getter_updater(p_getter, key):
        def deeper_getter(response_body, *args, **kwargs):
            return p_getter(response_body["aggregations"][key], *args, **kwargs)
        return deeper_getter
    getters = {key: getter_updater(aggs[aggr]["getters"][key], aggr) for aggr in aggs for key in aggs[aggr]["getters"]}
    axis = lambda x: {}
    for agg2 in aggs:
        if "axis" in aggs[agg2]:
            axis = getter_updater(aggs[agg2]["axis"], agg2)
    return {"body": body, "getters": getters, "axis": axis}


##############################################################################################
# QUERIES                                                                                    #
##############################################################################################


def query_filter(flt):
    return {
        "filtered":
        {
            "filter": flt
        }
    }


##############################################################################################
# FILTERS                                                                                    #
##############################################################################################


def flt_and(*args):
    return {
        "bool":
        {
            "must": args
        }
    }


def flt_exc(*args):
    return {
        "bool": {
            "must_not": args
        }
    }


def flt_or(*args):
    return {
        "bool": {
            "should": args
        }
    }


def flt_eq(field, value):
    if isinstance(value, list):
        return {"terms": {field: value}}
    elif isinstance(value, str) and value[-1] == '*':
        return {"prefix": {field: value[:-1]}}
    return {"term": {field: value}}


def flt_exists(field):
    return {"exists": {"field": field}}


def flt_range(field, left=None, right=None, left_is_strict=False, right_is_strict=False):
    return {"range": {field: {**({"gt" + ("" if left_is_strict else "e"): left} if left is not None else {}), **({ "lt" + ("" if right_is_strict else "e"): right} if right is not None else {})}}}


##############################################################################################
# BUCKET AGGS                                                                                #
##############################################################################################


@bucket_agg
def agg_filter(flt, getter_name=None, **kwargs):
    getters = {}
    add_getter(getters, getter_name, "doc_count")

    body = {"filter": flt}

    return {"body": body, "getters": getters, "getter_updater": single_bucket_getter_updater, "aggs": kwargs, "axis_maker": single_bucket_axis_maker}


@bucket_agg
def agg_terms(field, script=False, size=10000, min_doc_count=None, order=None, getter_doc_count=None, getter_key=None, is_axis=True, **kwargs):
    getters = {}
    add_getter(getters, getter_doc_count, "doc_count")
    add_getter(getters, getter_key, "key")

    def getter_factory(key, bucket_id=None):
        def result_plain(response_body, *args, **kwargs2):
            return [getters[key](bucket) for bucket in response_body["buckets"]]

        def result_axis(response_body, bucket_id, *args, **kwargs2):
            return getters[key](response_body["buckets"][bucket_id])

        def split_factory(bucket_key):
            def result_split(response_body, *args, **kwargs2):
                b_id = None
                for index, bucket in enumerate(response_body["buckets"]):
                    if bucket["key"] == bucket_key:
                        b_id = index
                        pass
                    pass
                if b_id is None:
                    return None
                return getters[key](response_body["buckets"][b_id])
            return result_split

        if isinstance(is_axis, list):
            return {key + "_" + str(key2): split_factory(key2) for key2 in is_axis}
            pass
        elif is_axis:
            return {key: result_axis}
        else:
            return {key: result_plain}

    getters_new={}
    for getter in getters:
        getters_new = {**getters_new, **getter_factory(getter)}

    if isinstance(is_axis, list):
        getter_updater = split_multi_bucket_getter_updater_factory(is_axis)
    elif is_axis:
        getter_updater = axis_multi_bucket_getter_updater
    else:
        getter_updater = plain_multi_bucket_getter_updater

    body = {"terms": {
        **{"script" if script else "field": field, "size": size},
        **({"min_doc_count": min_doc_count} if min_doc_count is not None else {}),
        **({"order": order} if order is not None else {})}
    }
    if is_axis and not isinstance(is_axis, list):
        return {"body": body, "getters": getters_new, "getter_updater": getter_updater, "aggs": kwargs, "axis_maker": multi_bucket_axis_maker}
    else:
        return {"body": body, "getters": getters_new, "getter_updater": getter_updater, "aggs": kwargs}


@bucket_agg
def agg_histogram(field, interval, getter_doc_count=None, getter_key=None, getter_key_as_string=None, date_histogram=False, is_axis=True, **kwargs):
    getters = {}
    add_getter(getters, getter_doc_count, "doc_count")
    add_getter(getters, getter_key, "key")
    add_getter(getters, getter_key_as_string, "key_as_string")
    if not date_histogram and getter_key_as_string is not None:
        raise ValueError("getter_key_as_string cannot be specified in usual histogram")

    def getter_factory(key):
        def result_plain(response_body, *args, **kwargs2):
            return [getters[key](bucket) for bucket in response_body["buckets"]]

        def result_axis(response_body, bucket_id, *args, **kwargs2):
            return getters[key](response_body["buckets"][bucket_id])

        def split_factory(bucket_key):
            def result_split(response_body, *args, **kwargs2):
                b_id = None
                for index, bucket in enumerate(response_body["buckets"]):
                    if bucket["key"] == bucket_key:
                        b_id = index
                        pass
                    pass
                if b_id is None:
                    return None
                return getters[key](response_body["buckets"][b_id])
            return result_split

        if isinstance(is_axis, list):
            return {key + "_" + str(key2): split_factory(key2) for key2 in is_axis}
            pass
        elif is_axis:
            return {key: result_axis}
        else:
            return {key: result_plain}

    getters_new = {}
    for getter in getters:
        getters_new = {**getters_new, **getter_factory(getter)}

    if isinstance(is_axis, list):
        getter_updater = split_multi_bucket_getter_updater_factory(is_axis)
    elif is_axis:
        getter_updater = axis_multi_bucket_getter_updater
    else:
        getter_updater = plain_multi_bucket_getter_updater

    body = {"date_histogram" if date_histogram else "histogram": {"field": field, "interval": interval}}

    if is_axis and not isinstance(is_axis, list):
        return {"body": body, "getters": getters_new, "getter_updater": getter_updater, "aggs": kwargs, "axis_maker": multi_bucket_axis_maker}
    else:
        return {"body": body, "getters": getters_new, "getter_updater": getter_updater, "aggs": kwargs}


##############################################################################################
# VALUE AGGS                                                                                 #
##############################################################################################


def simple_value_agg(agg):
    def decorated_agg (*args, getter=None, **kwargs):
        getters = {}
        add_getter(getters, getter, "value")

        body = agg(*args, **kwargs)

        return {"body": body, "getters": getters}
    return decorated_agg


def agg_top_hits(size, sorting=None, fields=None, **kwargs):
    body = {
        "top_hits":
        {
            "size": size,
            **(
                {
                    "sort":
                    {
                        skey:
                        {
                            "order": sorting[skey]
                        } for skey in sorting
                    }
                } if sorting is not None else {}
            ),
            **(
                {
                    "_source":
                    {
                        "includes": fields
                    }
                } if fields is not None else {}
            )
        }
    }
    return {"body": body, "getters": {}}


@simple_value_agg
def agg_cardinality(field, precision_threshold=40000, **kwargs):
    return {"cardinality": {"field": field, "precision_threshold": precision_threshold}}


@simple_value_agg
def agg_sum(field, script=False, **kwargs):
    return {"sum": {("script" if script else "field"): field}}


@simple_value_agg
def agg_avg(field, script=False, **kwargs):
    return {"avg": {("script" if script else "field"): field}}


@simple_value_agg
def agg_min(field, script=False, **kwargs):
    return {"min": {("script" if script else "field"): field}}


@simple_value_agg
def agg_max(field, script=False, **kwargs):
    return {"max": {("script" if script else "field"): field}}


def agg_extended_stats(field, script=False, sigma=3,
                       getter_count=None, getter_min=None, getter_max=None, getter_avg=None,
                       getter_sum=None, getter_sum_of_squares=None, getter_variance=None,
                       getter_deviation=None, getter_deviation_upper=None, getter_deviation_lower=None, **kwargs):
    getters = {}

    add_getter(getters, getter_count, "count")
    add_getter(getters, getter_min, "min")
    add_getter(getters, getter_max, "max")
    add_getter(getters, getter_avg, "avg")
    add_getter(getters, getter_sum, "sum")
    add_getter(getters, getter_sum_of_squares, "sum_of_squares")
    add_getter(getters, getter_variance, "variance")
    add_getter(getters, getter_deviation, "std_deviation")
    add_getter(getters, getter_deviation_upper, "upper", additional_level="std_deviation_bounds")
    add_getter(getters, getter_deviation_lower, "lower", additional_level="std_deviation_bounds")

    body = {"extended_stats": {("script" if script else "field"): field, "sigma": sigma}}

    return {"body": body, "getters": getters}

