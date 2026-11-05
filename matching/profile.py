import re
import unicodedata

# Editable role aliases. Seniority is an independent, mandatory condition.
ROLES = (
    'IT', 'IT Support', 'IT Support Specialist', 'Texniki yardım', 'Helpdesk operator', 'Support Technician', 'IT technician', 'IT texnik', 'İT üzrə', 'İT mütəxəssis',
    'IT specialist', 'IT operations', 'IT administrator', 'IT engineer', 'IT mühəndis', 'IT üzrə texnik', 'ICT support', 'İKT üzrə', 'İKT mütəxəssis',
    'Helpdesk', 'Help Desk', 'Service Desk', 'Desktop Support', 'Technical Support',
    'Texniki dəstək', 'İT dəstək', 'İT dəstəyi', 'İstifadəçi dəstəyi',
    'İnformasiya texnologiyaları', 'İnformasiya texnologiyaları üzrə dəstək',
    'Kompüter texniki', 'Kompüter üzrə texnik', 'SOC', 'SOC Analyst', 'Security Operations',
    'Cybersecurity', 'Cyber Security', 'Kibertəhlükəsizlik', 'Kiber təhlükəsizlik',
    'InfoSec', 'Cyber Defense', 'Cyber Defence', 'Kiber müdafiə', 'Information Security', 'İnformasiya təhlükəsizliyi', 'IT Security',
    'İT təhlükəsizliyi', 'Security Analyst', 'Blue Team', 'Threat Hunting',
    'Incident Response', 'Təhlükəsizlik əməliyyatları', 'Şəbəkə təhlükəsizliyi',
    'Network Security', 'System Administrator', 'Systems Administrator', 'Sysadmin',
    'Sistem administrator', 'Sistem inzibatçı', 'Network Engineer', 'Network Administrator',
    'Şəbəkə mühəndis', 'Şəbəkə inzibatçı', 'Şəbəkə administrator',
)
LEVEL = re.compile(r'\b(?:junior|jr|interns?|internships?|trainees?|entry level|ki[cç]ik|'
                   r'tecrubec\w*|staj[cy]\w*|tecrube proqram\w*|tecrube kec\w*)\b')
EXCLUDED = re.compile(r'\b(?:senior|sr|lead|head|principal|manager|middle|mid|mudiri?|rehber\w*|aparici|bas|mid(?:dle)? level|'
                      r'data (?:and |ve |uzre )?(?:analy\w*|analit\w*|scien\w*|engineer\w*)|'
                      r'(?:melumat\w*|verilen\w*) (?:uzre )?anali\w*|biznes analitik\w*|business analyst|business intelligence|bi analyst)\b')


def normalized(text):
    text = unicodedata.normalize('NFKD', text.casefold()).replace('ı', 'i').replace('ə', 'e')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[^\W_]+', text))


def eligible(job):
    title = normalized(job.title)
    employment = normalized(job.employment)
    if EXCLUDED.search(title):
        return False
    return bool(LEVEL.search(title + ' ' + employment) or employment in {'tecrube', 'staj'}
                or title.endswith((' tecrube', ' staj')))


def role_hits(text, words, *, in_description=False):
    text = ' ' + normalized(text) + ' '
    hits = []
    for word in words:
        phrase = normalized(word)
        if not phrase or (in_description and phrase == 'it'):
            continue
        # Allow Azerbaijani occupational suffixes (mühəndisi, inzibatçısı, texniki).
        if (' ' + phrase + ' ') in text or (
            phrase.endswith(('muhendis', 'inzibatci', 'texnik', 'mutexessis', 'administrator'))
            and any((' ' + phrase + ending + ' ') in text for ending in ('i', 'u', 'si', 'su'))
        ):
            hits.append(word)
    return hits
