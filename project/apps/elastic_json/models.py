from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

import django.db.models.options as options


options.DEFAULT_NAMES = options.DEFAULT_NAMES + (
    'es_index_name', 'es_type_name', 'es_mapping'
)


class University(models.Model):
    name = models.CharField(max_length=255, unique=True)


class Course(models.Model):
    name = models.CharField(max_length=255, unique=True)


class Student(models.Model):
    YEAR_IN_SCHOOL_CHOICES = (
        ('FR', 'Freshman'),
        ('SO', 'Sophomore'),
        ('JR', 'Junior'),
        ('SR', 'Senior'),
    )
    # note: incorrect choice in MyModel.create leads to creation of incorrect record
    year_in_school = models.CharField(
        max_length=2, choices=YEAR_IN_SCHOOL_CHOICES)
    age = models.SmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    # various relationships models
    university = models.ForeignKey(University, null=True, blank=True)
    courses = models.ManyToManyField(Course, null=True, blank=True)

    class Meta:
        es_index_name = 'django'
        es_type_name = 'student'
        # we make some assumptions:
        # 1. all model's fields have same names in elasticsearch index.
        # 2. django's id is stored in _id field
        # 3. in case you want autocomplete - name the field xxx_complete
        #    and provide get_es_xxx method.
        # 4. in case you want to put related objects - please, name them
        #    in the same way like in model.
        es_mapping = {
            "_id": {
                "store": True,
                'index': 'not_analyzed'
            },
            'properties': {
                # so that we're able to filter or generate facets based on university
                # here, we could've used pure university_name, but this is just
                # an example to illustrate elasticsearch/django
                'university': {
                    'type': 'object',
                    "_id": {
                        "store": True,
                        'index': 'not_analyzed'
                    },
                    'properties': {
                        'name': {'type': 'string', 'index': 'not_analyzed'},
                    }
                },
                'first_name': {'type': 'string', 'index': 'not_analyzed'},
                'last_name': {'type': 'string', 'index': 'not_analyzed'},
                'age': {'type': 'short'},
                'year_in_school': {'type': 'string'},
                'name_complete': {
                    'type': 'completion',
                    'analyzer': 'simple',
                    'payloads': True,  # note that we have to provide payload while updating
                    'preserve_separators': True,
                    'preserve_position_increments': True,
                    'max_input_length': 50,
                },
                # as elasticsearch doesn't require array to be specified, we
                # just put string here. As a result, this will be list of strings.
                "course_names": {
                    "type": "string", "store": "yes", "index": "not_analyzed",
                    'method': 'get_es_course_names'
                },
            }
        }

    def es_repr(self):
        data = {}
        mapping = self._meta.es_mapping
        if not isinstance(mapping, dict) or not mapping.get('properties'):
            raise TypeError('bad configuration of elasticsearch mapping')

        if mapping.get('_id'):
            data['_id'] = self.pk

        properties = mapping['properties']
        for field_name, config in properties.iteritems():
            if config['type'] == 'object':
                try:
                    related_object = getattr(self, field_name)
                    obj_data = {}
                    if config.get('_id'):
                        obj_data['_id'] = related_object.pk
                        for prop in config['properties'].keys():
                            obj_data[prop] = getattr(related_object, prop)
                except AttributeError:
                    obj_data = getattr(self, 'get_es_%s' % field_name)()
                data[field_name] = obj_data

            elif config['type'] == 'completion':
                data[field_name] = getattr(self, 'get_es_%s' % field_name)()

            else:
                if config.get('method'):
                    data[field_name] = getattr(self, config['method'])()
                else:
                    data[field_name] = getattr(self, field_name)
        return data

    def get_es_name_complete(self):
        return {
            "input": [self.first_name, self.last_name],
            "output": "%s %s" % (self.first_name, self.last_name),
            "payload": {"pk": self.pk},
        }

    def get_es_course_names(self):
        if not self.courses.exists():
            return []
        return [c.name for c in self.courses.all()]
