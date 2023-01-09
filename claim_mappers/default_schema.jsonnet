local claims = {
  email_verified: false,
} + std.extVar('claims');

{
  identity: {
    traits: {
      [if 'email' in claims && claims.email_verified then 'email' else null]: claims.email,
      [if 'name' in claims]: claims.name,
      [if 'given_name' in claims]: claims.given_name,
      [if 'family_name' in claims]: claims.family_name,
      [if 'last_name' in claims]: claims.last_name,
      [if 'middle_name' in claims]: claims.middle_name,
      [if 'nickname' in claims]: claims.nickname,
      [if 'preferred_username' in claims]: claims.preferred_username,
      [if 'profile' in claims]: claims.profile,
      [if 'picture' in claims]: claims.picture,
      [if 'website' in claims]: claims.website,
      [if 'gender' in claims]: claims.gender,
      [if 'birthdate' in claims]: claims.birthdate,
      [if 'zoneinfo' in claims]: claims.zoneinfo,
      [if 'locale' in claims]: claims.locale,
      [if 'phone_number' in claims && claims.phone_number_verified then 'phone_number' else null]: claims.phone_number,
      [if 'locale' in claims]: claims.locale,
      [if 'team' in claims]: claims.team,
    },
  },
}

