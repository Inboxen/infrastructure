##
#    Copyright (C) 2013-2014 Jessica Tallon & Matt Molyneaux
#
#    This file is part of Inboxen.
#
#    Inboxen is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Inboxen is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with Inboxen.  If not, see <http://www.gnu.org/licenses/>.
##

import hashlib
import random
import string
from types import StringTypes
from datetime import datetime

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from django.conf import settings
from django.db import IntegrityError, models
from django.db.models.query import QuerySet
from django.utils.encoding import smart_bytes
from django.utils.translation import ugettext as _


from pytz import utc

class HashedQuerySet(QuerySet):
    def hash_it(self, data):
        hashed = hashlib.new(settings.COLUMN_HASHER)
        hashed.update(smart_bytes(data))
        hashed = "{0}:{1}".format(hashed.name, hashed.hexdigest())

        return hashed

class InboxQuerySet(QuerySet):
    def create(self, length=settings.INBOX_LENGTH, domain=None, **kwargs):
        """Create a new Inbox, with a local part of `length`"""
        domain_model = self.model.domain.field.rel.to

        if not isinstance(domain, domain_model):
            raise domain_model.DoesNotExist(_("You need to provide a Domain object for an Inbox"))

        while True:
            # loop around until we create a unique address
            inbox = []
            for i in range(length):
                inbox += random.choice(string.ascii_lowercase)

            try:
                return super(InboxQuerySet, self).create(
                    inbox="".join(inbox),
                    created=datetime.now(utc),
                    domain=domain,
                    **kwargs
                )

            except IntegrityError:
                pass

    def from_string(self, email="", user=None, deleted=False):
        """Returns an Inbox object or raises DoesNotExist"""
        inbox, domain = email.split("@", 1)

        inbox = self.filter(inbox=inbox, domain__domain=domain)

        if deleted is True:
            inbox = inbox.filter(flags=self.model.flags.deleted)
        elif deleted is False:
            inbox = inbox.filter(flags=~self.model.flags.deleted)

        if user is not None:
            inbox = inbox.filter(user=user)

        inbox = inbox.get()

        return inbox

##
# Email managers
##

class HeaderQuerySet(HashedQuerySet):
    def create(self, name=None, data=None, ordinal=None, hashed=None, **kwargs):
        if hashed is None:
            hashed = self.hash_it(data)

        name_model = self.model.name.field.rel.to
        data_model = self.model.data.field.rel.to

        name = name_model.objects.only('id').get_or_create(name=name)[0]
        data, created = data_model.objects.only('id').get_or_create(hashed=hashed, defaults={'data':data})

        return (super(HeaderQuerySet, self).create(name=name, data=data, ordinal=ordinal, **kwargs), created)

    def get_many(self, *args, **kwargs):
        group_by = kwargs.pop("group_by", None)
        query = models.Q()
        for item in args:
            query = query | models.Q(name__name=item)

        values = self.filter(query)
        if group_by is None:
            values = values.values_list("name__name", "data__data")
            return OrderedDict(values)

        values = values.values_list(group_by, "name__name", "data__data")

        headers = OrderedDict()
        for value in values:
            part = headers.get(value[0], OrderedDict())
            part[value[1]] = value[2]
            headers[value[0]] = part

        return headers

class BodyQuerySet(HashedQuerySet):
    def get_or_create(self, data=None, hashed=None, **kwargs):
        if hashed is None:
            hashed = self.hash_it(data)

        return super(BodyQuerySet, self).get_or_create(hashed=hashed, defaults={'data':data}, **kwargs)
