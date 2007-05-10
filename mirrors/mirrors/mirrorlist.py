import cherrypy
import turbogears
from turbogears import controllers, expose, validate, redirect, widgets, validators, error_handler, exception_handler
from sqlobject import *
from sqlobject.sqlbuilder import *
from mirrors.model import *
from mirrors.IPy import IP
from mirrors.lib import uniqueify
import GeoIP

gi = GeoIP.new(GeoIP.GEOIP_STANDARD)

# key is strings in tuple (repo.prefix, arch)
mirrorlist_cache = {}

# key is an IPy.IP structure, value is list of host ids
host_netblock_cache = {}

# key is hostid, value is list of countries to allow
host_country_allowed_cache = {}



def trim(input):
    """ remove all but http and ftp URLs,
    and if both http and ftp are offered,
    leave only http"""
    l = {}
    for hostid, country, hcurl, siteprivate, hostprivate in input:
        us = hcurl.split('/')
        uprotocol = us[0]
        umachine = us[2]
        if not l.has_key(hostid):
            l[hostid] = {}
        l[hostid][uprotocol] = (hostid, country, hcurl, siteprivate, hostprivate)

    result = []
    for k, v in l.iteritems():
        if v.has_key(u'http:'):
            result.append(v[u'http:'])
        elif v.has_key(u'ftp:'):
            result.append(v[u'ftp:'])

    return result



def populate_repo_cache(repo):
    category = repo.category
    directory = repo.directory
    path = directory.name[len(category.topdir.name)+1:]
    sql  = 'SELECT host.id, host.country, host_category_url.url, site.private, host.private '
    sql += 'FROM host_category_dir, host_category, host_category_url, host, site '
    sql += 'WHERE host_category_dir.host_category_id = host_category.id ' # join criteria
    sql += 'AND   host_category_url.host_category_id = host_category.id ' # join criteria
    sql += 'AND   host_category.host_id = host.id '                       # join criteria
    sql += 'AND   host.site_id = site.id '                                # join criteria
    sql += 'AND host_category.category_id = %d ' % category.id # but select only the target category
    sql += "AND host_category_dir.path = '%s' " % path # and target path
    sql += 'AND host_category_dir.up2date '
    sql += 'AND NOT host_category_url.private '
    sql += 'AND host.user_active AND site.user_active '
    sql += 'AND host.admin_active AND site.admin_active '

    result = repo._connection.queryAll(sql)

    result = trim(result)
    newresult = {'global': [], 'byCountry':{}, 'byHostId':{}}
    for (hostid, country, hcurl, siteprivate, hostprivate) in result:
        country = country.upper()
        v = (hostid, "%s/%s" % (hcurl, path))
        if not siteprivate and not hostprivate:
            newresult['global'].append(v)

            if not newresult['byCountry'].has_key(country):
                newresult['byCountry'][country] = [v]
            else:
                newresult['byCountry'][country].append(v)

        if not newresult['byHostId'].has_key(hostid):
            newresult['byHostId'][hostid] = [v]
        else:
            newresult['byHostId'][hostid].append(v)

    global mirrorlist_cache
    mirrorlist_cache[(repo.prefix, repo.arch.name)] = newresult

def populate_netblock_cache():
    cache = {}
    for host in Host.select():
        if host.is_active() and len(host.netblocks) > 0:
            for n in host.netblocks:
                try:
                    ip = IP(n.netblock)
                except:
                    continue
                if cache.has_key(ip):
                    cache[ip].append(host.id)
                else:
                    cache[ip] = [host.id]

    global host_netblock_cache
    host_netblock_cache = cache

def populate_host_country_allowed_cache():
    cache = {}
    for host in Host.select():
        if host.is_active() and len(host.countries_allowed) > 0:
            cache[host.id] = [c.country.upper() for c in host.countries_allowed]
    global host_country_allowed_cache
    host_country_allowed_cache = cache
    

def populate_all_caches():
    populate_host_country_allowed_cache()
    populate_netblock_cache()
    for r in Repository.select():
        populate_repo_cache(r)
    print "mirrorlist caches populated"


def get_repo_cache(*args, **kwargs):
    if not kwargs.has_key('repo') or not kwargs.has_key('arch'):
        return
    repo = kwargs['repo']

    if u'source' in kwargs['repo']:
        kwargs['arch'] = u'source'

    if mirrorlist_cache.has_key((repo, arch)):
        return mirrorlist_cache[(repo, arch)]
    else:
        raise KeyError


def client_netblocks(ip):
    result = []
    try:
        clientIP = IP(ip)
    except:
        return result
    for k,v in host_netblock_cache.iteritems():
        if clientIP in k:
            result.extend(v)
    return result

def client_in_host_allowed(clientCountry, hostID):
    if host_country_allowed.has_key(hostID):
        if clientCountry.upper() in host_country_allowed[hostID]:
            return True
        return False
    return True



def trim_by_client_country(hostresults, clientCountry):
    if clientCountry is None:
        return hostresults

    results = []

    for hostid, hcurl in hostresults:
        if not host_country_allowed_cache.has_key(hostid):
            results.append((hostid, hcurl))
        else:
            if clientCountry in host_country_allowed_cache[hostid]:
                results.append((hostid, hcurl))

    return results



def mirrorlist_magic(*args, **kwargs):
    if not kwargs.has_key('repo') or not kwargs.has_key('arch'):
        return [(None, '# either repo= or arch= not speficied')]

    if u'source' in kwargs['repo']:
        kwargs['arch'] = u'source'
    repo = kwargs['repo']
    arch = kwargs['arch']

    header = "# repo = %s arch = %s " % (repo, arch)
    if not mirrorlist_cache.has_key((repo, arch)):
        return [(None, header + 'error: invalid repo or arch')]
    cache = mirrorlist_cache[(repo, arch)]

    if kwargs.has_key('ip'):
        client_ip = kwargs['ip']
    else:
        client_ip = cherrypy.request.headers.get("X-Forwarded-For")
        if client_ip is None:
            client_ip = cherrypy.request.remote_addr
        #client_ip = '143.166.1.1'
    clientCountry = gi.country_code_by_addr(client_ip)

    # handle netblocks
    if not kwargs.has_key('country'):
        hosts = client_netblocks(client_ip)
        if len(hosts) > 0:
            hostresults = []
            for hostId in hosts:
                if cache['byHostId'].has_key(hostId):
                    hostresults.extend(cache['byHostId'][hostId])
                    header += 'Using preferred netblock'
            if len(hostresults) > 0:
                message = [(None, header)]
                return message + hostresults

    # handle country request lists
    if kwargs.has_key('country'):
        requestedCountries = uniqueify([c.upper() for c in kwargs['country'].split(',') ])
        if 'GLOBAL' in requestedCountries:
            hostresults = trim_by_client_country(cache['global'], clientCountry)
            header += 'country = global'
            message = [(None, header)]
            return message + hostresults

        hostresults = []
        for c in requestedCountries:
            if cache['byCountry'].has_key(c):
                hostresults.extend(cache['byCountry'][c])
                header += 'country = %s' % c
        hostresults = trim_by_client_country(hostresults, clientCountry)

        # if not enough per-country mirrors, return the global list
        if len(hostresults) < 3:
            hostresults = trim_by_client_country(cache['global'], clientCountry)
            header += ' country = global'
            message = [(None, header)]
            return message + hostresults

        
        message = [(None, header)]
        return message + hostresults

    # fall back to GeoIP-based lookups
    hostresults = []
    if cache['byCountry'].has_key(clientCountry):
        hostresults.extend(cache['byCountry'][clientCountry])
        header += 'country = %s ' % clientCountry
    hostresults = trim_by_client_country(hostresults, clientCountry)

    # if not enough per-country mirrors, return the global list
    # fixme should maybe return lists from countries on same continent
    if len(hostresults) < 3:
        hostresults = trim_by_client_country(cache['global'], clientCountry)
        header += 'country = global '
        message = [(None, header)]
        return message + hostresults

    header += ' country = %s' % clientCountry
    message = [(None, header)]
    return message + hostresults

def do_mirrorlist(*args, **kwargs):
    results = mirrorlist_magic(*args, **kwargs)
    results =  [url for hostid, url in results]
    return dict(values=results)
