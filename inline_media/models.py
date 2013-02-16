#-*- coding: utf-8 -*-

import hashlib
import os
import os.path

from django.db import models
from django.db.models.signals import pre_delete
from django.contrib.contenttypes.models import ContentType
from django.core import urlresolvers
from django.utils.translation import ugettext_lazy as _

from sorl.thumbnail import get_thumbnail, ImageField
from sorl.thumbnail.default import Storage
from tagging.fields import TagField

from inline_media.conf import settings

storage = Storage()

#----------------------------------------------------------------------
# InlineType code borrowed from django-basic-apps by Nathan Borror
# https://github.com/nathanborror/django-basic-apps

class InlineType(models.Model):
    """InlineType model"""
    title           = models.CharField(max_length=200)
    content_type    = models.ForeignKey(ContentType)

    class Meta:
        db_table = 'inline_types'

    def __unicode__(self):
        return self.title


#----------------------------------------------------------------------
LICENSES = (('http://artlibre.org/licence/lal/en',
             'Free Art License'),
            ('http://creativecommons.org/licenses/by/2.0/',
             'CC Attribution'),
            ('http://creativecommons.org/licenses/by-nd/2.0/',
             'CC Attribution-NoDerivs'),
            ('http://creativecommons.org/licenses/by-nc-nd/2.0/',
             'CC Attribution-NonCommercial-NoDerivs'),
            ('http://creativecommons.org/licenses/by-nc/2.0/',
             'CC Attribution-NonCommercial'),
            ('http://creativecommons.org/licenses/by-nc-sa/2.0/',
             'CC Attribution-NonCommercial-ShareAlike'),
            ('http://creativecommons.org/licenses/by-sa/2.0/',
             'CC Attribution-ShareAlike'))

class License(models.Model):
    """Licenses under whose terms and conditions media is publicly accesible""" 

    name = models.CharField(max_length=255)
    link = models.URLField(unique=True)
    tags = TagField(help_text=_("i.e: creativecommons, comercial, "
                                "non-commercial, ..."))

    class Meta:
        db_table = 'inline_media_licenses'

    def homepage(self):
        return '<a href="%s" target="_new">%s</a>' % tuple([self.link]*2)
    homepage.allow_tags = True

    def __unicode__(self):
        return self.name

#----------------------------------------------------------------------
# find_duplicates idea borrowed from django-filer by Stefan Foulis
# https://github.com/stefanfoulis/django-filer.git

class PictureManager(models.Manager):
    def find_duplicates(self, pic):
        return [ p for p in self.exclude(pk=pic.pk).filter(sha1=pic.sha1) ]
        

class Picture(models.Model):
    """Picture model"""

    title = models.CharField(max_length=255)
    picture = ImageField(upload_to="pictures/%Y/%b/%d", storage=storage)
    show_as_link = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    show_description_inline = models.BooleanField(_("Show description inline"),
                                                  default=True)
    author = models.CharField(blank=True, null=False, max_length=255,
                              help_text=_("picture's author"))
    show_author = models.BooleanField(default=False)
    license = models.ForeignKey(License, blank=True, null=True)
    show_license = models.BooleanField(default=False)
    uploaded = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    sha1 = models.CharField(max_length=40, db_index=True, 
                            blank=True, default="")
    tags = TagField(help_text=_("i.e: logo, photo, country, season, ..."))

    objects = PictureManager()

    class Meta:
        ordering = ('-uploaded',)
        db_table = 'inline_media_pictures'

    def save(self, *args, **kwargs):
        try:
            sha = hashlib.sha1()
            self.picture.seek(0)
            sha.update(self.picture.read())
            self.sha1 = sha.hexdigest()
        except Exception, e:
            self.sha1 = ""
        super(Picture, self).save(*args, **kwargs)

    def __unicode__(self):
        return '%s' % self.title

    @property
    def url(self):
        return '%s%s' % (settings.MEDIA_URL, self.picture)

    # showing duplicates ala django-filer
    @property
    def duplicates(self):
        return Picture.objects.find_duplicates(self)

    def get_admin_url_path(self):
        return urlresolvers.reverse(
            'admin:%s_%s_change' % (self._meta.app_label,
                                    self._meta.module_name,),
            args=(self.pk,)
        )

    # used in admin 'list_display' to show the thumbnail of self.picture
    def thumbnail(self):
        try:
            im = get_thumbnail(self.picture, "x50")
        except Exception, e:
            return "unavailable"
        return '<div style="text-align:center"><img src="%s"></div>' % im.url
    thumbnail.allow_tags = True


def delete_picture(sender, instance, **kwargs):
    if sender == Picture:
        instance.picture.delete()
pre_delete.connect(delete_picture, sender=Picture)


class PictureSet(models.Model):
    """ PictureSet model """
    title = models.CharField(
        help_text=_("Visible at the top of the gallery slider that shows up "
                    "when clicking on cover's picture."), max_length=255)
    slug = models.SlugField()
    description = models.TextField(
        help_text=_("Only visible in the inline under sizes "
                    "small, medium, large or full."), blank=True)
    show_description_inline = models.BooleanField(default=True)
    cover = models.ForeignKey("Picture", blank=True, null=True,
                              help_text=_("Front cover picture."))
    pictures = models.ManyToManyField("Picture", related_name="picture_sets")
    order = models.CommaSeparatedIntegerField(
        blank=True, max_length=512, 
        help_text=_("Establish pictures order by typing the comma "
                    "separated list of their picture IDs."))
    show_counter = models.BooleanField(
        default=False, help_text=_("Whether to show how many pictures "
                                   "contains the pictureset."))
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    tags = TagField(help_text=_("i.e: exposition, holidays, party, ..."))
    
    class Meta:
        db_table = "inline_media_picture_sets"
  
    def __unicode__(self):
        return "%s" % self.title

    # used in admin 'list_display' to show the thumbnail of self.picture
    def cover_thumbnail(self):
        im = get_thumbnail(self.cover.picture, "x50")
        return '<div style="text-align:center"><img src="%s"></div>' % im.url
    cover_thumbnail.allow_tags = True

    # used in admin 'list_display' to show the list of pictures' titles
    def picture_titles_as_ul(self):
        titles = []
        for picture in self.next_picture():
            if picture == self.cover:
                titles.append("<li>%s (cover)</li>" % picture.title)
            else:
                titles.append("<li>%s</li>" % picture.title)
        return '<ul>%s</ul>' % "".join(titles)
    picture_titles_as_ul.allow_tags = True

    def next_picture(self):
        if self.order:
            picids = [ int(pid) for pid in self.order.split(',') ]
            for picid in picids:
                yield self.pictures.get(pk=picid)
        else:
            for picture in self.pictures.all():
                yield picture
