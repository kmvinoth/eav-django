# -*- coding: utf-8 -*-

from django.db.models import Manager


class BaseEntityManager(Manager):

    # TODO: refactor filter() and exclude()   -- see django.db.models.manager and ...query

    def exclude(self, *args, **kw):
        qs = self.get_query_set().exclude(*args)
        for lookup, value in kw.items():
            lookups = self._filter_by_lookup(qs, lookup, value)
            qs = qs.exclude(**lookups)
        return qs

    def filter(self, *args, **kw):
        """
        A wrapper around standard filter() method. Allows to construct queries
        involving both normal fields and EAV attributes without thinking about
        implementation details. Usage::

            ConcreteEntity.objects.filter(rubric=1, price=2, colour='green')

        ...where `rubric` is a ForeignKey field, and `colour` is the name of an
        EAV attribute represented by Schema and Attr models.
        """

        qs = self.get_query_set().filter(*args)
        for lookup, value in kw.items():
            lookups = self._filter_by_lookup(qs, lookup, value)
            qs = qs.filter(**lookups)
        if __debug__: print qs.query.as_sql()
        return qs

    def _filter_by_lookup(self, qs, lookup, value):
        fields   = self.model._meta.get_all_field_names()
        schemata = dict((s.name, s) for s in self.model.get_schemata_for_model())

        if '__' in lookup:
            name, sublookup = lookup.split('__')
        else:
            name, sublookup = lookup, None

        if name in fields:
            # ordinary model field
            return {lookup: value}
        elif name in schemata:
            # EAV attribute (Attr instance linked to entity)
            schema = schemata.get(name)
            if schema.datatype == schema.TYPE_MANY:
                #if sublookup:
                #    # TODO: enable '__in' and such
                #    raise NameError('%s is not a valid lookup: sublookups cannot '
                #                    'be used with m2m attributes.' % lookup)
                return self._filter_by_m2m_schema(qs, name, sublookup, value, schema)
            else:
                if __debug__: print 'schema %s has no choices defined.' % schema
                return self._filter_by_simple_schema(qs, lookup, sublookup, value, schema)
        else:
            raise NameError('Cannot filter items by attributes: unknown '
                            'attribute "%s". Available fields: %s. '
                            'Available schemata: %s.' % (name,
                            ', '.join(fields), ', '.join(schemata)))

    def _filter_by_simple_schema(self, qs, lookup, sublookup, value, schema):
        """
        Filters given entity queryset by an attribute which is linked to given
        schema and has given value in the field for schema's datatype.
        """
        value_lookup = 'attrs__value_%s' % schema.datatype
        if sublookup:
            value_lookup = '%s__%s' % (value_lookup, sublookup)
        return {
            'attrs__schema': schema,
            str(value_lookup): value
        }

    def _filter_by_m2m_schema(self, qs, lookup, sublookup, value, schema):
        """
        Filters given entity queryset by an attribute which is linked to given
        many-to-many schema.
        """
        schemata = dict((s.name, s) for s in self.model.get_schemata_for_model())   # TODO cache this dict, see above too
        try:
            schema = schemata[lookup]
        except KeyError:
            # TODO: smarter error message, i.e. how could this happen and what to do
            raise ValueError(u'Could not find schema for lookup "%s"' % lookup)
        sublookup = '__%s'%sublookup if sublookup else ''
        return {
            'attrs__schema': schema,
            'attrs__choice__name%s'%sublookup: value,  # TODO: can we filter by id, not name?
        }

    def create(self, **kwargs):
        """
        Creates entity instance and related Attr instances.

        Note that while entity instances may filter schemata by fields, that
        filtering does not take place here. Attribute of any schema will be saved
        successfully as long as such schema exists.

        Note that we cannot create attribute with no pre-defined schema because
        we must know attribute type in order to properly put value into the DB.
        """

        fields = self.model._meta.get_all_field_names()
        schemata = dict((s.name, s) for s in self.model.get_schemata_for_model())

        # check if all attributes are known
        possible_names = set(fields) | set(schemata.keys())
        wrong_names = set(kwargs.keys()) - possible_names
        if wrong_names:
            raise NameError('Cannot create %s: unknown attribute(s) "%s". '
                            'Available fields: (%s). Available schemata: (%s).'
                            % (self.model._meta.object_name, '", "'.join(wrong_names),
                               ', '.join(fields), ', '.join(schemata)))

        # init entity with fields
        instance = self.model(**dict((k,v) for k,v in kwargs.items() if k in fields))

        # set attributes; instance will check schemata on save
        for name, value in kwargs.items():
            setattr(instance, name, value)

        # save instance and EAV attributes
        instance.save(force_insert=True)

        return instance

'''
class BaseSchemaManager(Manager):

    def for_form(self, *args, **kw):
        return self.filter(choices=None, *args, **kw)

    def for_lookups(self, *args, **kw):
        return self.filter(datatype__not=self.model.TYPE_MANY, *args, **kw)
'''