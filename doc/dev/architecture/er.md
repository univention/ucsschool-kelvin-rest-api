classDiagram
  class school{
    *INTEGER id NOT NULL
    JSON administrative_servers NOT NULL
    VARCHAR<255> class_share_file_server
    JSON display_name NOT NULL
    JSON educational_servers NOT NULL
    VARCHAR<255> home_share_file_server
    VARCHAR<255> name NOT NULL
    UUID public_id NOT NULL
    VARCHAR<255> record_uid NOT NULL
    VARCHAR<255> source_uid NOT NULL
  }
  class group{
    *INTEGER id NOT NULL
    JSON display_name NOT NULL
    VARCHAR<255> email
    INTEGER group_type_id NOT NULL
    BOOLEAN has_share NOT NULL
    VARCHAR<255> name NOT NULL
    UUID public_id NOT NULL
    VARCHAR<255> record_uid NOT NULL
    INTEGER school_id NOT NULL
    VARCHAR<255> source_uid NOT NULL
  }
  class user{
    *INTEGER id NOT NULL
    BOOLEAN active NOT NULL
    DATE birthday
    VARCHAR<255> email
    DATE expiration_date
    VARCHAR<255> firstname NOT NULL
    VARCHAR<255> lastname NOT NULL
    VARCHAR<255> name NOT NULL
    UUID public_id NOT NULL
    VARCHAR<255> record_uid NOT NULL
    VARCHAR<255> source_uid NOT NULL
  }
  class role{
    *INTEGER id NOT NULL
    JSON display_name NOT NULL
    VARCHAR<255> name NOT NULL
    UUID public_id NOT NULL
  }
  class school_membership{
    *INTEGER id NOT NULL
    BOOLEAN is_primary NOT NULL
    INTEGER primary_user_constraint
    INTEGER school_id NOT NULL
    INTEGER user_id NOT NULL
  }
  class group_type{
    *INTEGER id NOT NULL
    JSON display_name NOT NULL
    VARCHAR<255> name NOT NULL
  }
  class group_member_association{
    *INTEGER group_id NOT NULL
    *INTEGER school_membership_id NOT NULL
  }
  class group_role_association{
    *INTEGER group_id NOT NULL
    *INTEGER role_id NOT NULL
  }
  class school_membership_role_association{
    *INTEGER role_id NOT NULL
    *INTEGER school_membership_id NOT NULL
  }
  class group_user_email_senders_association{
    *INTEGER group_id NOT NULL
    *INTEGER user_id NOT NULL
  }
  class group_group_email_senders_association{
    *INTEGER child_group_id NOT NULL
    *INTEGER parent_group_id NOT NULL
  }
  class legal_guardian_association{
    *INTEGER legal_guardian_id NOT NULL
    *INTEGER legal_ward_id NOT NULL
  }
  school "1" -- "0..n" group
  group_type "1" -- "0..n" group
  user "1" -- "0..n" school_membership
  school "1" -- "0..n" school_membership
  school_membership "1" -- "0..n" group_member_association
  group "1" -- "0..n" group_member_association
  group "1" -- "0..n" group_role_association
  role "1" -- "0..n" group_role_association
  school_membership "1" -- "0..n" school_membership_role_association
  role "1" -- "0..n" school_membership_role_association
  group "1" -- "0..n" group_user_email_senders_association
  user "1" -- "0..n" group_user_email_senders_association
  group "1" -- "1" group_group_email_senders_association
  group "1" -- "1" group_group_email_senders_association
  user "1" -- "1" legal_guardian_association
  user "1" -- "1" legal_guardian_association