# -*- coding: utf-8 -*-
"""
Celery tasks
"""
#
# Univention UCS@school
#
# Copyright 2017 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

from __future__ import absolute_import, unicode_literals
import time
import logging
from celery import shared_task
from celery.utils.log import get_task_logger
from celery.signals import task_postrun
from django.core.exceptions import ObjectDoesNotExist
from ucsschool.importer.exceptions import InitialisationError
from .models import UserImportJob, Logfile, JOB_STARTED, JOB_FINISHED, JOB_ABORTED, JOB_SCHEDULED
from .http_api_import_frontend import HttpApiImportFrontend


logger = get_task_logger(__name__)
logger.level = logging.DEBUG


def run_import_job(task, importjob_id):
	try:
		importjob = UserImportJob.objects.get(pk=importjob_id)
	except ObjectDoesNotExist as exc:
		logger.exception(str(exc))
		raise
	timeout = 60
	while importjob.status != JOB_SCHEDULED:
		# possible race condition: we write JOB_STARTED into DB before client
		# (UserImportJobSerializer) writes JOB_SCHEDULED into DB
		time.sleep(1)
		importjob.refresh_from_db()
		timeout -= 1
		if timeout <= 0:
			raise InitialisationError('UserImportJob {} did not reache JOB_SCHEDULED state in 60s.'.format(importjob_id))
	runner = HttpApiImportFrontend(importjob, task, logger)
	importjob.log_file = Logfile.objects.create(path=runner.logfile_path)
	importjob.status = JOB_STARTED
	importjob.save(update_fields=('status', 'log_file'))

	res = runner.main()

	importjob = UserImportJob.objects.get(pk=importjob_id)
	importjob.status = JOB_ABORTED if res else JOB_FINISHED
	importjob.save(update_fields=('status',))
	if res:
		raise Exception('Import job exited with {}.'.format(res))


@shared_task(bind=True)
def import_users(self, importjob_id):
	logger.info('Starting UserImportJob %d (%r).', importjob_id, self)
	run_import_job(self, importjob_id)
	logger.info('Finished UserImportJob %d.', importjob_id)
	return 'UserImportJob #{} ended successfully.'.format(importjob_id)


@shared_task(bind=True)
def dry_run(self, importjob_id):
	logger.info('Starting dry run %d (%r).', importjob_id, self)
	run_import_job(self, importjob_id)
	logger.info('Finished dry run %d.', importjob_id)
	return 'Dry run of UserImportJob #{} ended successfully.'.format(importjob_id)


@task_postrun.connect
def taskresult_save_callback(sender=None, headers=None, body=None, **kwargs):
	"""
	Update progress on UserImportJob and remove additional task logger handler.

	:param sender: celery task instance
	:param headers: None
	:param body: None
	:param kwargs: dict:
	:return: None
	"""
	try:
		ij = UserImportJob.objects.get(task_id=kwargs['task_id'])
		ij.update_progress()
		task_handler_name = 'import job {}'.format(ij.pk)
		for handler in logger.handlers[:]:
			if handler.name == task_handler_name:
				logger.removeHandler(handler)
				logger.info('Removed logging handler for UserImportJob %r.', ij.pk)
	except ObjectDoesNotExist:
		logger.error('Could not find an UserImportJob for TaskResult %r.', kwargs['task_id'])