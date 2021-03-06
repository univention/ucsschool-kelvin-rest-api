User import configuration file reference
========================================

Configuration files are interpreted in a hierarchical way.
*Please read global_configuration_readme.txt first!*

After reading the global configuration options (1. and 2.), module specific
configuration is read. In case of the user import, those are:

3. /usr/share/ucs-school-import/configs/user_import_defaults.json (do not edit)
4. /var/lib/ucs-school-import/configs/user_import.json (edit this)

After that follow
5. Configuration file set on the command line.
6. Options set on the command line by --set and its aliases.


[1]: mandatory
[2]: default value for [3]
[3]: if this is not set, fall back to [2]


"factory": str: fully dotted path to (a subclass of) ucsschool.importer.default_user_import_factory.DefaultUserImportFactory
"classes": {
	"reader": str: fully dotted path to a subclass of BaseReader e.g. "ucsschool.importer.reader.csv_reader.CsvReader"
	"import_user":  str: fully dotted path to a *function* that returns an object of the appropriate subclass of ImportUser
	"mass_importer":  str: fully dotted path to a subclass of ucsschool.importer.mass_import.mass_import.MassImport
	"password_exporter":  str: fully dotted path to a subclass of ucsschool.importer.writer.result_exporter.ResultExporter
	"result_exporter":  str: fully dotted path to a subclass of ucsschool.importer.writer.result_exporter.ResultExporter
	"user_importer":  str: fully dotted path to a subclass of ucsschool.importer.mass_import.user_import.UserImport
	"username_handler":  str: fully dotted path to a subclass of ucsschool.importer.utils.username_handler.UsernameHandler
	"user_writer":  str: fully dotted path to a subclass of ucsschool.importer.writer.base_writer.BaseWriter
},
"input": {
	"type": str [1]: "csv", "json", "socket" etc
	"filename": str: path to the input file (csv etc)
},
"activate_new_users": {
	"default":           bool [2]: if the new user should be activated
	"student":           bool [3]: if the new user should be activated
	"staff":             bool [3]: if the new user should be activated
	"teacher":           bool [3]: if the new user should be activated
	"teacher_and_staff": bool [3]: if the new user should be activated
},
"csv": {
	"allowed_missing_columns": list(str): names of columns for which no error will be raised if they are missing.
	                                      Allows the use of the same configuration file for input files with different
	                                      data.
	"delimiter": str: character that separates the cells of two columns, will be auto-detected if not set
	"header_lines": int: how many line to skip, if 1, first line will be used to create keys for dict
	"incell-delimiter": {
		"default":               str [2]: multi-value field separator symbol, separates two values inside a cell
    	<udm attribute name>:    str [3]:                (not between columns like "delimiter", defaults to ',')
	}
	"mapping": {
		key: value -> str: str
		           -> 'value' must be either the name of an Attribute as supported by the ImportUser class
		              or it will used as a key in a dict 'udm_attribute'. Data from 'udm_attribute' will
		              be written to the underlying UDM object.
	}
},
"deletion_grace_period": {
        "deactivation": int: number of days until the user account is deactivated. If set to 0, the account is deactivated
                             immediately. This option will be ignored if deletion_grace_period:deletion is set to 0. The
                             default value is 0.
        "deletion":     int: number of days until the user account is deleted. If set to 0, the user is deleted immediately,
                             otherwise the property "ucsschoolPurgeTimestamp" is set to the future delete date.
                             A cron job will delete the user account on that date.
}
"scheme" [1]: {
	"email": str: schema of email address, variables may be used as described in manual-4.2:users:templates
	"record_uid": str [1]: schema of record_uid, variables may be used as described in manual-4.2:users:templates
	"username" [1]: {
		"default":           str [2]: schema of username, variables may be used
		"student":           str [3]:                     as described in manual-4.2:users:templates
		"staff":             str [3]:                     plus [COUNTER2] which is replaced by numbers
		"teacher":           str [3]:                     starting from 2 or [ALWAYSCOUNTER] which is
		"teacher_and_staff": str [3]:                     always replaced by numbers starting from 1.
	},
	<udm attribute name>:	str: scheme (manual-4.2:users:templates) to create a UDM attribute from
},
"maildomain": str: value of 'maildomain' variable that can be used in scheme->email. If unset will try to find one in system.
"mandatory_attributes": list: list of UDM attribute names that must be set by the import
"no_delete": bool: if set to True, users missing in the input will not be deleted in LDAP.
"output": {
	"new_user_passwords": str: path to the new users passwords file, datetime.strftime() will be used on
	                           it to format any time format strings
	"user_import_summary": str: path to a file to write the summary in CSV fomat to, datetime.strftime() will be applied
},
"password_length": int [1]: length of the random password generated for new users
"school": str: name (abbreviation) of school this import is for, if not available from input
"school_classes_invalid_character_replacement": str: invalid characters in class names (valid are digits, ascii-characters and the characters '- ._') will be replaced with this string.
"school_classes_keep_if_empty": bool: if true, a users school_classes attribute will not be changed, when it is set to empty
"workgroups_invalid_character_replacement": str: invalid characters in class names (valid are digits, ascii-characters and the characters '- ._') will be replaced with this string.
"workgroups_keep_if_empty": bool: if true, a users workgroups attribute will not be changed, when it is set to empty
"source_uid": str [1]: UID of source database
"tolerate_errors": int [1]: number of non-fatal errors to tolerate before aborting, -1 means unlimited
"user_deletion": DEPRECATED - use deletion_grace_period instead,
"user_role": str: if set, all new users from input will have that role (student|staff|teacher|teacher_and_staff)
"username": {
	"allowed_special_chars": str [1]:   characters that are allowed in usernames, additionally to a-z, A-Z and 0-9.
	                                    Defaults to only the dot. To add the hyphen, use ".-" (a string, not a list).
	                                    The characters listed here will never be used as first or last character in a
	                                    username.
	"max_length": {                     IMPORTANT:
	                                    * Users with usernames longer than 20 characters are excluded from the support
	                                    regarding Samba, Samba4 connector app and Active Directory connector app.
	                                    If using a "max_length" value above 20, users with usernames shorter than 21 are
	                                    still supported.
	                                    * The value must not be higher than the value of the UCR variable
	                                    ucsschool/username/max_length.
	                                    * If Window clients < 8.1 are in use, the maximum username lenght must
	                                    not exceed 20, or logging into them will not be possible!
	                                    * If scheme:username contains a COUNTER variable the maximum length of a
	                                    username will be reduced by 3 for counter digits.
	                                    * For students the maximum length of a username will be further reduced by the
	                                    length of the "exam-" prefix (usually "exam-", so by 5).
		"default":           int [2]:	maximum length of a username for all user roles not explicitely defined, default: 20.
		"student":           int [3]: 	maximum length of a students username, default: 15 (20 - length of "exam-" prefix).
		"staff":             int [3]: 	see "default".
		"teacher":           int [3]: 	see "default".
		"teacher_and_staff": int [3]: 	see "default".
	}
}
