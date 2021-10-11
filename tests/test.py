from __future__ import print_function

import unittest
from datetime import datetime, timedelta

from TMSSync import attendance as att


class AttendanceTest(unittest.TestCase):

    IN = 1
    OUT = 2

    uid = 9600509
    start = datetime(2018, 8, 25)

    emp = None

    @classmethod
    def delete_stuff(cls):
        cls.get_employee()
        att.FPEntry.delete_by_emp(cls.emp, cls.start)
        att.AttendanceDetail.delete_by_emp(cls.emp, cls.start)
        att.EmployeeAttendance.delete_by_emp(cls.emp, cls.start)

    @classmethod
    def make_entry(cls, status=IN, **kwargs):
        print ('.', end='')
        t = cls.start + timedelta(**kwargs)
        att.FPEntry(
                cls.uid, status, t.strftime('%Y%m%d'), t.strftime('%H%M%S')
        ).record()

    @classmethod
    def get_employee(cls):
        if cls.emp is None:
            cls.emp = att.Employee.get_by_code(cls.uid)
        return cls.emp

    @classmethod
    def setUpClass(cls):
        print ('Getting Employee ...')
        cls.get_employee()
        print ('Preparing ...')
        cls.delete_stuff()

        att.EmployeeAttendance(
                cls.start + timedelta(days=7),
                employee=cls.get_employee(),
                attendanceStatus='A').save()

        print ('Making Entries ', end='')
        # two hours session on a saturday (25th)
        cls.make_entry(cls.IN, days=0, hours=11, minutes=30)
        cls.make_entry(cls.OUT, days=0, hours=13, minutes=30)

        # monday (27th) longer than full day session
        cls.make_entry(cls.IN, days=2, hours=9, minutes=0)
        cls.make_entry(cls.OUT, days=2, hours=20, minutes=30)

        # multiday session tuesday (28th) to thursday (30th)
        cls.make_entry(cls.IN, days=3, hours=7, minutes=30)
        cls.make_entry(cls.OUT, days=5, hours=15)

        # entry on Sunday (2nd) after absence on friday (31st), saturday (1st)
        cls.make_entry(cls.IN, days=8, hours=12)

        # session on monday (3rd) after missing an out entry on sunday
        cls.make_entry(cls.IN, days=9, hours=11)
        cls.make_entry(cls.OUT, days=9, hours=18)

        # monday (3rd) evening entries with messed up order
        cls.make_entry(cls.OUT, days=9, hours=20)
        cls.make_entry(cls.IN, days=9, hours=19)

        # only session on wednesday (5th) is after hours
        cls.make_entry(cls.IN, days=11, hours=20)
        cls.make_entry(cls.OUT, days=11, hours=21)

        # on thursday (6th) a solitary IN late entry after an early start
        # session
        cls.make_entry(cls.IN, days=12, hours=8, minutes=30)
        cls.make_entry(cls.OUT, days=12, hours=9, minutes=30)
        cls.make_entry(cls.IN, days=12, hours=11, minutes=15)

        # delayed addition for tuesday (4th)
        cls.make_entry(cls.IN, days=10, hours=10)
        cls.make_entry(cls.OUT, days=10, hours=19)
        print (' Done!')

        print ('Gettings Sessions and Attendances ...')
        # get all session and attendance entries after start

        cls.sessions = att.Session.get_latest_by_emp(cls.emp, cls.start)
        cls.atts = att.EmployeeAttendance.get_latest_by_emp(cls.emp, cls.start)

        cls.print_sessions()
        cls.print_attendances()

        print ('Running Tests ', end='')

    @classmethod
    def tearDownClass(cls):
        cls.get_employee()
        cls.delete_stuff()

    def test_employee(self):
        self.get_employee()
        self.assertEqual(self.emp.employeeCode, self.uid)

    def test_earlier_entries(self):
        ee = att.AttendanceDetail.get_earlier_entry(
                self.emp, self.start)
        ps = att.Session.get_previous_session(self.emp, self.start)
        self.assertLess(ee.inOutTime, self.start)
        self.assertEqual(ps.inTime, ee.inOutTime)

    @classmethod
    def print_entries(cls):
        print ('Entries:')
        for ses in cls.sessions:
            print (ses.in_entry)
            print (ses.out_entry)

    @classmethod
    def print_sessions(cls):
        print ('Sessions:')
        for ses in cls.sessions:
            print (ses)

    @classmethod
    def print_attendances(cls):
        print ('Attendance:')
        for at in cls.atts:
            print (at)

    def test_make_an_entry(self):
        ses = self.sessions[0]
        att = self.atts[0]

        self.assertIsNotNone(ses.outTime)
        self.assertEqual(ses.outTime - ses.inTime, timedelta(hours=2))
        self.assertEqual(att.attendanceDate, self.start)
        self.assertEqual(att.attendanceStatus, 'P')
        self.assertEqual(att.timeStatus, 'InTime')

    def test_after_holiday_early_start(self):
        sunday = self.atts[1]
        monday = self.atts[2]
        monday_session = self.sessions[1]
        self.assertEqual(sunday.attendanceStatus, 'Holiday')
        self.assertEqual(monday.attendanceStatus, 'P')
        self.assertEqual(monday.timeStatus, 'InTime')
        self.assertEqual(
                monday_session.outTime - monday_session.inTime,
                timedelta(hours=11, minutes=30))

    def test_multi_day_session_split(self):
        tuesday = self.atts[3]
        wednesday = self.atts[4]
        thursday = self.atts[5]
        tue_before = self.sessions[2]
        tue_after = self.sessions[3]
        thursday_after = self.sessions[4]

        self.assertEqual(tuesday.attendanceStatus, 'P')
        self.assertEqual(tuesday.timeStatus, 'InTime')
        self.assertEqual(wednesday.attendanceStatus, 'A')
        self.assertEqual(thursday.attendanceStatus, 'P')
        self.assertEqual(tuesday.timeStatus, 'InTime')

        self.assertEqual(tue_before.outTime, datetime(2018, 8, 28, 9, 59, 59))
        self.assertEqual(tue_before.outType, 'soft')
        self.assertEqual(tue_after.outTime, datetime(2018, 8, 29, 9, 59, 59))
        self.assertEqual(tue_after.outType, 'soft')
        self.assertEqual(thursday_after.inTime, datetime(2018, 8, 30, 10))

    def test_absent(self):
        friday = self.atts[6]
        self.assertEqual(friday.attendanceStatus, 'A')

    def test_optional_holiday(self):
        saturday = self.atts[7]
        self.assertEqual(saturday.attendanceStatus, 'Holiday')
        self.assertEqual(saturday.description, 'Optional')

    def test_overtime_holiday(self):
        sunday = self.atts[8]
        self.assertEqual(sunday.attendanceStatus, 'P')
        self.assertEqual(sunday.timeStatus, 'OverTime')

    def test_multiple_in_outs(self):
        sunday_session = self.sessions[5]
        monday_session1 = self.sessions[6]
        monday_session2 = self.sessions[7]
        monday = self.atts[9]
        self.assertEqual(sunday_session.outTime, datetime(2018, 9, 2, 16, 15))
        self.assertEqual(sunday_session.outType, 'soft')
        self.assertEqual(monday_session1.outTime - monday_session1.inTime,
                         timedelta(hours=7))
        self.assertEqual(monday_session2.outTime - monday_session2.inTime,
                         timedelta(hours=1))
        self.assertEqual(monday.attendanceStatus, 'P')
        self.assertEqual(monday.timeStatus, 'Late')

    def test_present_when_updated_later(self):
        tuesday = self.atts[10]
        tuesday_session = self.sessions[8]
        self.assertEqual(tuesday.attendanceStatus, 'P')
        self.assertEqual(tuesday.timeStatus, 'InTime')
        self.assertEqual(
                tuesday_session.outTime - tuesday_session.inTime,
                timedelta(hours=9))

    def test_absent_if_session_outside_shift(self):
        wednesday = self.atts[11]
        wednesday_after = self.sessions[9]
        self.assertEqual(wednesday.attendanceStatus, 'A')
        self.assertEqual(wednesday_after.outTime - wednesday_after.inTime,
                         timedelta(hours=1))

    def test_early_entry(self):
        thursday_early = self.sessions[10]
        self.assertEqual(
                thursday_early.outTime - thursday_early.inTime,
                timedelta(hours=1))
        self.assertEqual(thursday_early.in_entry.trackDate,
                         datetime(2018, 9, 5))

    def test_open_ended_session(self):
        thursday = self.atts[12]
        thursday_after = self.sessions[11]
        self.assertEqual(thursday.attendanceStatus, 'P')
        self.assertEqual(thursday.timeStatus, 'Late')
        self.assertIsNone(thursday_after.outTime)


if __name__ == "__main__":
    unittest.main()
