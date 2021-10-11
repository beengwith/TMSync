from __future__ import print_function

from datetime import datetime, timedelta

from . import connection


Connection = connection.Connection


LATE_GRACE_TIME = timedelta(minutes=30)
MAX_EARLY_START_OFFSET = timedelta(hours=2, minutes=15)
IN_SHIFT_SESSION_DURATION = timedelta(hours=4, minutes=15)
EXT_SHIFT_SESSION_DURATION = timedelta(hours=2, minutes=15)


class DayDetail(object):
    saturday_optional = True

    WEEKEND = 'Weekend'
    OPTIONAL = 'Optional'

    @classmethod
    def get(self, date):
        date = datetime(date.year, date.month, date.day)
        today = date.strftime('%A')
        hday = Connection().execute(
            'Select Description from DayDetails Where todayDate=?',
            date).fetchone()
        if hday:
            return hday[0]

        weekend = Connection().execute(
            "Select 'Weekend' from Weekend Where Weekend=?", today).fetchone()

        if weekend:
            return weekend[0]

        if self.saturday_optional and today == 'Saturday':
            return 'Optional'

        return ''


class ShiftDetails(object):
    grace_time = LATE_GRACE_TIME
    early_offset = MAX_EARLY_START_OFFSET

    def __init__(self, timeFrom, timeTo, employeeId=None, employee=None):
        self._timeFrom = timeFrom.time()
        self._timeTo = timeTo.time()
        self._employee = employee
        self.employeeId = employeeId
        if employee:
            self.employeeId = employee.employeeId

    def __str__(self):
        return 'ShiftDetails(%s, %s, employee=%s)' % (
                self.timeFrom, self.timeTo, self.employee.employeeCode)

    @property
    def timeFrom(self):
        return self._timeFrom

    @property
    def timeTo(self):
        return self._timeTo

    @property
    def employee(self):
        if self._employee is None:
            self._employee = Employee.get(self.employeeId)
        return self._employee

    def start_time(self, trackDate):
        return datetime(trackDate.year, trackDate.month, trackDate.day,
                        self._timeFrom.hour, self._timeFrom.minute)

    def end_time(self, trackDate):
        return datetime(trackDate.year, trackDate.month, trackDate.day,
                        self._timeTo.hour, self._timeTo.minute)

    def get_day_end(self, _trackDate):
        trackDate = _trackDate + timedelta(days=1)
        return datetime(trackDate.year, trackDate.month, trackDate.day,
                        self._timeFrom.hour, self._timeFrom.minute)

    @classmethod
    def get_by_emp(cls, employee):
        query = ('Select timeFrom, timeTo, employeeId '
                 'From ShiftDetails '
                 'Where SDID = ( '
                 'Select Max(SDID) From ShiftDetails Where EmployeeID = ?)')
        data = Connection().execute(query, employee.employeeId).fetchone()
        return cls(*data, employee=employee) if data else None

    def get_track_date(self, dt, allow_early_start=False):
        shifted_time = dt - timedelta(
                hours=self._timeFrom.hour,
                minutes=self._timeFrom.minute)
        if allow_early_start:
            shifted_time += self.early_offset
        date = shifted_time.date()
        return datetime(date.year, date.month, date.day)

    def is_early_start(self, dt):
        early_date = self.get_track_date(dt, allow_early_start=True)
        track_date = self.get_track_date(dt)
        if early_date != track_date:
            return True
        return False

    def is_same_day(self, dt1, dt2, allow_early_start=False):
        return (self.get_track_date(dt1, allow_early_start) ==
                self.get_track_date(dt2, allow_early_start))

    def is_late(self, inTime, td=None, allow_early_start=False):
        if td is None:
            td = self.get_track_date(inTime, allow_early_start)
        return inTime >= self.start_time(td) + self.grace_time

    def is_between(self, time, td=None, allow_early_start=False):
        if td is None:
            td = self.get_track_date(time, allow_early_start)
        if time >= self.start_time(td) and time < self.end_time(td):
            return True
        return False

    def is_after(self, time, td=None, allow_early_start=False):
        if td is None:
            td = self.get_track_date(time, allow_early_start)
        return time >= self.end_time(td)

    def is_before(self, time, td=None, allow_early_start=False):
        if td is None:
            td = self.get_track_date(time, allow_early_start)
        return self.is_early_start(time) or time < self.start_time(td)


class Employee(object):
    def __init__(self, id, code, name, status, shift=None):
        self.employeeId = int(id)
        self.employeeCode = int(code)
        self.employeeName = str(name)
        self.status = bool(status)
        self._shift = shift

    def __repr__(self):
        return 'Employee(%d, %d, "%s")' % (self.employeeId, self.employeeCode,
                                           self.employeeName)

    @classmethod
    def get_by_code(cls, code):
        query = '''
            select
                employeeId, employeecode, employeename, employeestatus
            from employee
            where employeecode = ? '''
        data = Connection().execute(query, str(code)).fetchone()
        return cls(*data) if data else None

    @classmethod
    def get(cls, id):
        query = '''
            select
                employeeId, employeecode, employeename, employeestatus
            from employee
            where employeeId = ?'''
        cur = Connection().execute(query, id).fetchone()
        return cls(*cur) if cur else None

    @property
    def shift(self):
        if self._shift is None:
            self._shift = ShiftDetails.get_by_emp(self)
        return self._shift


class EmployeeAttendance(object):
    class Status:
        PRESENT = P = 'P'
        ABSENT = A = 'A'
        ANNUAL_LEAVE = AL = 'AL'
        SICK_LEAVE = SL = 'SL'
        CASUAL_LEAVE = CL = 'CL'
        COMPENSATION = C = 'C'
        OFFICIAL_LEAVE = OL = 'Official Leave'
        GENERAL_LEAVE = GL = 'General Leave'
        OTHERS = O = 'Others'
        HOLIDAY = H = 'Holiday'
        OFFICIAL_TRIP = OT = 'Official Trip'
        MARRIAGE_LEAVE = ML = 'Marriage Leave'

    class TimeStatus:
        LATE = 'Late'
        INTIME = 'InTime'
        OVERTIME = 'OverTime'
        COMPENSATE = 'Compensate'
        NONE = ''

    def __init__(self,
                 attendanceDate,
                 attendanceStatus='',
                 timeStatus='',
                 description='',
                 employeeId=None,
                 eaid=None,
                 employee=None):
        self._eaid = eaid
        self.employeeId = employeeId
        self.attendanceDate = datetime(
            attendanceDate.year, attendanceDate.month, attendanceDate.day)
        self.attendanceStatus = attendanceStatus
        self.timeStatus = timeStatus
        self.description = description
        self.created = False
        self._employee = employee
        self.employeeId = employeeId
        if employee:
            self.employeeId = employee.employeeId
        if self.employeeId is None:
            raise ValueError('Must specify EmployeeId')

    @property
    def employee(self):
        if self._employee is None:
            self._employee = Employee.get(self.employeeId)
        return self._employee

    def __str__(self):
        return '<EmployeeAttendance %d, %s, %s, %s>' % (
                self.employee.employeeCode, self.attendanceDate,
                self.attendanceStatus, self.timeStatus)

    @classmethod
    def get_latest_by_emp(cls, employee, date_from):
        query = '''
            Select
                AttendanceDate, AttendanceStatus, timeStatus,
                description, EmployeeId, eaid
            From EmployeeAttendance
            Where
                employeeId = ? and AttendanceDate >= ?
            Order by
                AttendanceDate
        '''
        return [
            cls(*data, employee=employee)
            for data in Connection().execute(
                query, employee.employeeId, date_from)]

    @classmethod
    def get(cls, employee, attendanceDate):
        query = '''
            Select
                AttendanceDate, AttendanceStatus, timeStatus,
                description, EmployeeId, eaid
            From EmployeeAttendance
            Where employeeId = ? and AttendanceDate = ?
        '''
        data = Connection().execute(query, employee.employeeId,
                                    attendanceDate).fetchone()
        return cls(*data, employee=employee) if data else None

    def _get_eaid(self):
        query = '''
            Select eaid
            From EmployeeAttendance
            Where employeeId = ? and AttendanceDate = ?
        '''
        if self.created:
            data = Connection().execute(query, self.employeeId,
                                        self.attendanceDate).fetchone()
            self._eaid = data[0]
            self.created = False

    def save(self):
        self._get_eaid()
        if self._eaid is None:
            query = '''
                Insert Into
                EmployeeAttendance(employeeId, attendanceDate,
                        attendanceStatus, timeStatus, description)
                Values(?, ?, ?, ?, ?)'''
            Connection().execute(query, self.employeeId,
                                 self.attendanceDate, self.attendanceStatus,
                                 self.timeStatus, self.description)
            self.created = True
        else:
            query = '''
                Update EmployeeAttendance
                Set
                    AttendanceStatus=?, TimeStatus=?, description=?
                Where
                    EAID=?'''
            Connection().execute(query, self.attendanceStatus, self.timeStatus,
                                 self.description, self._eaid)

    @classmethod
    def delete_by_emp(cls, employee, timeFrom):
        query = '''
            Delete from EmployeeAttendance
            Where employeeId = ? and attendanceDate >= ? '''
        Connection().execute(query, employee.employeeId, timeFrom)

    @classmethod
    def delete_by_time(cls, timeFrom):
        query = 'Delete from EmployeeAttendance Where attendanceDate >= ?'
        Connection().execute(query, timeFrom)

    @classmethod
    def mark_present(cls, employee, att_date, late=None):
        att = cls.get(employee, att_date)
        save = False

        offday = DayDetail.get(att_date)
        optday = offday == DayDetail.OPTIONAL
        holiday = offday and not optday

        if offday:
            late = False

        if att is None:
            att = EmployeeAttendance(
                    att_date, employee=employee)
            save = True

        if att.attendanceStatus != cls.Status.P:
            att.attendanceStatus = cls.Status.P
            save = True

        if holiday:
            if att.timeStatus != cls.TimeStatus.OVERTIME:
                att.timeStatus = cls.TimeStatus.OVERTIME
                save = True

        elif late is not None:
            if late and att.timeStatus == '':
                att.timeStatus = cls.TimeStatus.LATE
                save = True
            elif not late and att.timeStatus in (cls.TimeStatus.LATE, ''):
                att.timeStatus = cls.TimeStatus.INTIME
                save = True

        if save:
            att.save()

    @classmethod
    def mark_absent(cls, employee, att_date):
        att = cls.get(employee, att_date)
        offday = DayDetail.get(att_date)

        status = cls.Status.A if not offday else cls.Status.H
        descr = (DayDetail.OPTIONAL
                 if offday == DayDetail.OPTIONAL else '')

        if att is None:
            att = cls(
                att_date,
                attendanceStatus=status,
                description=descr,
                employee=employee)
            att.save()

        else:
            save = False
            if (att.attendanceStatus in (cls.Status.H, cls.Status.A) and
                    att.attendanceStatus != status):
                att.attendanceStatus = status
                save = True
            if (att.description in (DayDetail.OPTIONAL, '') and
                    att.description != descr):
                att.description = descr
                save = True
            if save:
                att.save()


EAStatus = EmployeeAttendance.Status
TimeStatus = EmployeeAttendance.TimeStatus


class AttendanceDetail(object):
    class Types:
        SOFT = 'soft'
        COMPUTED = SOFT
        BIOMETRIC = BIOM = 'biometric'
        MANUAL = MANU = 'manual'
        SELF = 'self'
        CODE = 'code'

    class Status:
        IN = 'In'
        OUT = 'Out'

    def __init__(self,
                 inOutTime,
                 inOutStatus,
                 inOutType=Types.BIOM,
                 employeeId=None,
                 trackDate=None,
                 adid=None,
                 inOutId=None,
                 employee=None):
        self.employeeId = employeeId
        self.trackDate = trackDate
        self.inOutTime = inOutTime
        self.inOutStatus = inOutStatus
        self.inOutType = inOutType
        self._adid = adid
        self._inOutId = inOutId
        self._employee = employee
        if employee:
            self.employeeId = employee.employeeId
        if self.employeeId is None:
            raise ValueError('Must specify employee ID')
        self.created = False

    def __str__(self):
        return '<Attendance Detail: %s, %s, %r, %s >' % (
            self.employee.employeeCode, self.inOutStatus, self.inOutTime,
            self.inOutType)

    @property
    def employee(self):
        if self._employee is None:
            self._employee = Employee.get(self.employeeId)
        return self._employee

    def getInOutId(self):
        return self._inOutId

    def setInOutId(self, value):
        self._inOutId = value

    inOutId = property(getInOutId, setInOutId)

    @classmethod
    def get_latest_by_emp(cls, employee, time_from, status=Status.IN):
        query = '''
            Select
                inOutTime, inOutStatus, inOutType, employeeId, trackDate, adid,
                inOutId
            From
                AttendanceDetails
            Where
                employeeId = ? and inOutTime >= ? and inOutStatus = ?
            Order By
                inOutTime
        '''
        cur = Connection().execute(
                query, employee.employeeId, time_from, status)
        return [cls(*data, employee=employee) for data in cur]

    def get(self, adid):
        query = '''
            Select
                inOutTime, inOutStatus, inOutType, employeeId, trackDate, adid,
                inOutId
            From
                AttendanceDetails
            Where
                adid = ?
        '''
        data = Connection().execute(query, adid).fetchone()
        return AttendanceDetail(*data) if data else None

    @classmethod
    def get_by_inOutId(cls, employee, inOutId, inOutStatus):
        query = '''
            Select
                inOutTime, inOutStatus, inOutType, employeeId, trackDate, adid,
                inOutId
            From
                AttendanceDetails
            Where
                employeeId = ? and inOutId = ? and inOutStatus = ?   '''
        data = Connection().execute(query, employee.employeeId, inOutId,
                                    inOutStatus).fetchone()
        return cls(*data, employee=employee) if data else None

    @classmethod
    def generateInOutID(self, employeeId):
        query = '''
            Select IsNull(Max(InOutID),0) + 1
            from AttendanceDetails
            where EmployeeID = ?'''
        data = Connection().execute(query, employeeId).fetchone()
        return data[0]

    def _ensure_inOutId(self):
        if self._inOutId is None:
            if self.inOutStatus == self.Status.IN:
                self._inOutId = self.generateInOutID(self.employeeId)
            else:
                raise ValueError('Must Specify inOutId')

    def _get_adid(self):
        query = '''
        Select adid from AttendanceDetails
        Where employeeId = ? and inOutId = ?
        '''
        if self.created:
            data = Connection().execute(query, self.employeeId,
                                        self._inOutId).fetchone()
            self._adid = data[0]
            self.created = False

    def get_session(self):
        if self.inOutId is None:
            raise ValueError('Must Specify inOutId')
        if self.inOutStatus == self.Status.IN:
            out_entry = AttendanceDetail.get_by_inOutId(
                self.employee, self.inOutId, self.Status.OUT)
            return Session(self, out_entry)
        else:
            in_entry = AttendanceDetail.get_by_inOutId(
                self.employee, self.inOutId, self.Status.IN)
            return Session(in_entry, self)

    def _set_track_date(self):
        if self.trackDate is None:
            self.trackDate = self.employee.shift.get_track_date(self.inOutTime)

    def save(self):
        self._ensure_inOutId()
        self._get_adid()
        self._set_track_date()
        if self._adid is None:
            query = '''
                Insert INTO
                AttendanceDetails(InOutID, EmployeeID, TrackDate, InOutTime,
                    InOutStatus, inOutType)
                Values(?, ?, ?, ?, ?, ?);
            '''
            Connection().execute(
                    query, self.inOutId, self.employeeId, self.trackDate,
                    self.inOutTime, self.inOutStatus, self.inOutType)
        else:
            query = '''
                Update AttendanceDetails
                Set
                    TrackDate=?, inOutTime=?, InOutType=?
                Where
                    ADID = ?
            '''
            Connection().execute(query, self.trackDate, self.inOutTime,
                                 self.inOutType, self._adid)

    @classmethod
    def get_earlier_entry(cls, employee, time, inOutStatus=Status.IN):
        query = '''
        Select
            inOutTime, inOutStatus, inOutType, employeeId, trackDate, adid,
            inOutId
        From AttendanceDetails
        Where
            inOutTime < ? and inOutStatus = ? and employeeId = ?
        Order by
            inOutTime Desc
        '''
        data = Connection().execute(query, time, inOutStatus,
                                    employee.employeeId).fetchone()
        return cls(*data, employee=employee) if data else None

    @classmethod
    def get_later_entry(cls, employee, time, inOutStatus=Status.IN):
        query = '''
        Select
            inOutTime, inOutStatus, inOutType, employeeId, trackDate, adid,
            inOutId
        From AttendanceDetails
        Where
            inOutTime > ? and inOutStatus = ? and employeeId = ?
        Order by
            inOutTime
        '''
        data = Connection().execute(query, time, inOutStatus,
                                    employee.employeeId).fetchone()
        return cls(*data, employee=employee) if data else None

    @classmethod
    def delete_by_emp(cls, employee, timeFrom):
        query = '''
            Delete from AttendanceDetails
            Where employeeId = ? and inOutTime >= ? '''
        Connection().execute(query, employee.employeeId, timeFrom)

    @classmethod
    def delete_by_time(cls, timeFrom):
        query = ''' Delete from AttendanceDetails Where inOutTime >= ? '''
        Connection().execute(query, timeFrom)


ADStatus = AttendanceDetail.Status
ADTypes = AttendanceDetail.Types


class Session(object):

    early_offset = MAX_EARLY_START_OFFSET
    grace_inside = IN_SHIFT_SESSION_DURATION
    grace_outside = EXT_SHIFT_SESSION_DURATION

    def __init__(self, in_entry, out_entry=None):
        self.in_entry = in_entry
        self.out_entry = out_entry

    @property
    def employee(self):
        return self.in_entry.employee

    def inType():
        doc = "The inType property."

        def fget(self):
            return self.in_entry.inOutType

        def fset(self, value):
            self.in_entry.inOutType = value

        return locals()

    inType = property(**inType())

    def inTime():
        doc = "The inTime property."

        def fget(self):
            return self.in_entry.inOutTime

        def fset(self, value):
            self.in_entry.inOutTime = value

        return locals()

    inTime = property(**inTime())

    def outTime():
        doc = "The outTime property."

        def fget(self):
            if self.out_entry is not None:
                return self.out_entry.inOutTime

        def fset(self, value):
            if value is None:
                return
            if self.out_entry is None:
                self.make_out_entry(value)
            else:
                self.out_entry.inOutTime = value

        return locals()

    outTime = property(**outTime())

    def outType():
        doc = "The outType property."

        def fget(self):
            if self.out_entry is not None:
                return self.out_entry.inOutType

        def fset(self, value):
            if self.out_entry is not None:
                self.out_entry.inOutType = value

        return locals()

    outType = property(**outType())

    @property
    def trackDate(self):
        early_date = self.employee.shift.get_track_date(
                self.inTime + self.early_offset)
        if self.outTime is not None:
            out_date = self.employee.shift.get_track_date(self.outTime)
            if out_date < early_date:
                return out_date
        return early_date

    def __str__(self):
        return ('<Session: %s, %s (%s) --> %s (%s)>' % (
            self.employee.employeeCode, self.inTime, self.inType, self.outTime,
            self.outType))

    @classmethod
    def get_latest_by_emp(self, employee, time_from):
        return [
            _ad.get_session()
            for _ad in AttendanceDetail.get_latest_by_emp(
                employee, time_from)]

    def make_out_entry(self, time, typ=ADTypes.BIOM):
        self.out_entry = AttendanceDetail(
            time,
            ADStatus.OUT,
            inOutType=typ,
            inOutId=self.in_entry.inOutId,
            employee=self.in_entry.employee)

    def is_between(self, time):
        if self.outTime is not None:
            return time > self.inTime and time < self.outTime

    @classmethod
    def make(cls,
             employeeId=None,
             inTime=None,
             outTime=None,
             employee=None,
             inType=ADTypes.BIOM,
             outType=ADTypes.BIOM):
        in_entry = AttendanceDetail(
            inTime,
            ADStatus.IN,
            inOutType=inType,
            employeeId=employeeId,
            employee=employee)
        out_entry = None
        if outTime is not None:
            out_entry = AttendanceDetail(
                outTime,
                ADStatus.OUT,
                inOutType=outType,
                employeeId=employeeId,
                employee=employee)
        return Session(in_entry, out_entry)

    def save(self):
        self.in_entry.trackDate = self.trackDate
        self.in_entry.save()
        if self.out_entry is not None:
            self.out_entry.inOutId = self.in_entry.inOutId
            self.out_entry.trackDate = self.trackDate
            self.out_entry.save()

    @classmethod
    def get_previous_session(cls, employee, inTime):
        try:
            entry = AttendanceDetail.get_earlier_entry(employee, inTime)
            return entry.get_session()
        except AttributeError:
            return None

    @classmethod
    def get_next_session(cls, employee, inTime):
        try:
            return AttendanceDetail.get_later_entry(employee,
                                                    inTime).get_session()
        except AttributeError:
            return None

    def record(self):

        # mark absents
        prevSession = Session.get_previous_session(self.employee,
                                                   self.inTime)
        inDate = self.trackDate
        if prevSession:
            prevDate = self.employee.shift.get_track_date(prevSession.outTime)
        else:
            prevDate = inDate
        dateCounter = prevDate

        while dateCounter < inDate:
            EmployeeAttendance.mark_absent(self.employee, dateCounter)
            dateCounter += timedelta(days=1)

        # mark today
        shift = self.employee.shift
        dateCounter = inDate
        present = shift.is_between(self.inTime) or (
            self.outTime is not None and
            (self.inTime < shift.start_time(inDate) and
             (shift.is_after(self.outTime) or shift.is_between(self.outTime))))

        if present:
            EmployeeAttendance.mark_present(
                    self.employee, inDate,
                    late=shift.is_late(self.inTime, inDate, True))
        elif shift.is_after(self.inTime, inDate, True):
            EmployeeAttendance.mark_absent(self.employee, inDate)

        if self.outTime is not None:
            outDate = shift.get_track_date(self.outTime)
            dateCounter = inDate + timedelta(days=1)

            while dateCounter <= outDate:
                EmployeeAttendance.mark_present(self.employee, dateCounter)
                dateCounter += timedelta(days=1)

        self.save()

    def split_and_record(self):
        # split the session at shift start time
        if self.outTime is None:
            self.record()
            return

        # collect intervening shift times
        date_counter = self.trackDate.date()
        start_times, end_times = [], []

        while date_counter <= self.outTime.date():

            start_time = self.employee.shift.start_time(date_counter)
            end_time = self.employee.shift.end_time(date_counter)

            if self.is_between(start_time):
                start_times.append(start_time)

            if self.is_between(start_time):
                end_times.append(end_time)

            date_counter += timedelta(days=1)

        is_early_start = self.employee.shift.is_early_start(self.inTime)

        if ((is_early_start and len(start_times) > 1) or
                (not is_early_start and len(start_times) > 0)):

            # must split
            outTime = self.outTime
            outType = self.outType

            if outType == ADTypes.SOFT:
                make_two = False

                if self.employee.shift.is_early_start(self.inTime):
                    self.outTime = min(
                        start_times[0] + self.grace_inside, outTime)

                elif self.employee.shift.is_between(self.inTime):
                    self.outTime = min(
                        self.inTime + self.grace_inside,
                        outTime, end_times[0] + self.grace_outside)

                else:
                    self.outTime = min(
                        self.inTime + self.grace_outside, outTime)
                    if self.outTime > start_times[0]:
                        self.outTime = start_times[0] - timedelta(seconds=1)
                        make_two = True

                self.record()

                if make_two:
                    Session.make(
                            employee=self.employee,
                            inTime=start_times[0],
                            inType=ADTypes.SOFT,
                            outTime=start_times[0] + self.grace_inside,
                            outType=ADTypes.SOFT).record()

            else:
                if is_early_start:
                    # first split (long) only
                    self.outTime = start_times[1] - timedelta(seconds=1)
                    self.outType = ADTypes.SOFT
                    self.record()
                else:
                    # first split
                    self.outTime = start_times[0] - timedelta(seconds=1)
                    self.outType = ADTypes.SOFT
                    self.record()

                    # middle split
                    if len(start_times) > 1:
                        Session.make(
                            employee=self.employee,
                            inTime=start_times[0],
                            inType=ADTypes.SOFT,
                            outTime=start_times[1] - timedelta(seconds=1),
                            outType=ADTypes.SOFT).record()

                # end split
                Session.make(
                    employee=self.employee,
                    inTime=start_times[-1],
                    inType=ADTypes.SOFT,
                    outTime=outTime,
                    outType=outType).record()

        else:  # No need to split
            self.record()


class FPEntry(object):
    __tid_to_inout__ = {
        1: ADStatus.IN,
        2: ADStatus.OUT,
        3: ADStatus.IN,
        4: ADStatus.OUT,
        101: ADStatus.IN,
        102: ADStatus.OUT,
        201: ADStatus.IN,
        202: ADStatus.OUT,
        301: ADStatus.IN,
        302: ADStatus.OUT
    }

    __tid_to_type__ = {
        1: ADTypes.BIOM,
        2: ADTypes.BIOM,
        3: ADTypes.BIOM,
        4: ADTypes.BIOM,
        101: ADTypes.MANU,
        102: ADTypes.MANU,
        201: ADTypes.SELF,
        202: ADTypes.SELF,
        301: ADTypes.SOFT,
        302: ADTypes.SOFT
    }

    def __init__(self, empcode, tid, date, time):
        self._empcode = int(empcode)
        self.tid = int(tid)
        self.date = str(date)
        self.time = str(time)
        self._emp = None

    @property
    def empcode(self):
        return self._empcode

    @property
    def employee(self):
        if self._emp is None:
            self._emp = Employee.get_by_code(self.empcode)
        return self._emp

    @property
    def inOutStatus(self):
        return self.__tid_to_inout__.get(self.tid, ADStatus.IN)

    @property
    def typ(self):
        return self.__tid_to_type__.get(self.tid, ADTypes.BIOM)

    @property
    def datetime(self):
        return datetime.strptime(' '.join([self.date, self.time]),
                                 '%Y%m%d %H%M%S')

    def save(self):
        insert_sql = ('insert into '
                      'FPEntries(C_Date, C_Time, L_TID, L_UID) '
                      'Values(?, ?, ?, ?)')
        return Connection().execute(insert_sql, self.date, self.time, self.tid,
                                    self._empcode)

    def record(self):
        if self.employee is None:
            raise ValueError('No Employee')

        if self.inOutStatus == ADStatus.IN:
            ps = Session.get_previous_session(self.employee, self.datetime)
            if ps:
                if ps.outTime is None:
                    ps.outTime = self.datetime - timedelta(seconds=1)
                    ps.outType = ADTypes.SOFT
                    ps.split_and_record()
                    ns = Session.get_next_session(self.employee, self.datetime)
                    if ns:
                        if ns.inType == ADTypes.SOFT:
                            ns.inTime = self.datetime
                            ns.inType = self.typ
                            ns.split_and_record()
                        else:
                            s = Session.make(
                                employee=self.employee,
                                inTime=self.datetime,
                                inType=self.typ)
                            s.outTime = ns.inTime - timedelta(seconds=1)
                            s.outType = ADTypes.SOFT
                            s.split_and_record()
                    else:
                        Session.make(
                            employee=self.employee,
                            inTime=self.datetime,
                            inType=self.typ).split_and_record()
                else:
                    if ps.outTime > self.datetime:
                        Session.make(
                            employee=self.employee,
                            inTime=self.datetime,
                            inType=self.typ,
                            outTime=ps.outTime,
                            outType=ps.outType).split_and_record()
                        ps.outTime = self.datetime - timedelta(seconds=1)
                        if ps.outType != ADTypes.SOFT:
                            ps.outType = ADTypes.SOFT
                        ps.split_and_record()
                    else:
                        ns = Session.get_next_session(self.employee,
                                                      self.datetime)
                        if ns:
                            if ns.inType == ADTypes.SOFT:
                                ns.inTime = self.datetime
                                ns.inType = self.typ
                                ns.split_and_record()
                            else:
                                s = Session.make(
                                    employee=self.employee,
                                    inTime=self.datetime,
                                    inType=self.typ)

                                s.outTime = ns.inTime - timedelta(seconds=1)
                                s.outType = ADTypes.SOFT
                                s.split_and_record()
                        else:
                            Session.make(
                                employee=self.employee,
                                inTime=self.datetime,
                                inType=self.typ).split_and_record()

            else:  # when no previous session exist
                ns = Session.get_next_session(self.employee, self.datetime)
                if ns:
                    if ns.inType == ADTypes.SOFT:
                        ns.inTime = self.datetime
                        ns.inType = self.typ
                        ns.split_and_record()
                    else:
                        Session.make(
                            employee=self.employee,
                            inTime=self.datetime,
                            inType=self.typ,
                            outTime=ns.inTime - timedelta(seconds=1),
                            outType=ADTypes.SOFT).split_and_record()
                else:
                    Session.make(
                        employee=self.employee,
                        inTime=self.datetime,
                        inType=self.typ).split_and_record()
        else:  # when Entry is out
            ps = Session.get_previous_session(self.employee, self.datetime)
            if ps:
                if (ps.outTime is None or ps.outType == ADTypes.SOFT):
                    ps.outTime = self.datetime
                    ps.outType = self.typ
                    ps.split_and_record()
                else:
                    if ps.outTime < self.datetime:
                        new_ses = Session.make(
                            employee=self.employee,
                            outTime=self.datetime,
                            outType=self.typ,
                            inTime=self.datetime - timedelta(seconds=1),
                            inType=ADTypes.SOFT)
                        new_ses.split_and_record()
                    else:
                        Session.make(
                            employee=self.employee,
                            inTime=self.datetime + timedelta(seconds=1),
                            inType=ADTypes.SOFT,
                            outTime=ps.outTime,
                            outType=ps.outType).split_and_record()
                        ps.outTime = self.datetime
                        ps.outType = self.typ
                        ps.split_and_record()
            else:
                Session.make(
                    employee=self.employee,
                    outTime=self.datetime,
                    outType=self.typ,
                    inTime=self.datetime - timedelta(seconds=1),
                    inType=AttendanceDetail.Types.SOFT).split_and_record()
        self.save()

    @classmethod
    def delete_by_emp(cls, employee, time_from):
        query = '''
            Delete from FPEntries
            Where L_UID = ? and C_Date + C_Time >= ?'''
        return Connection().execute(
                query, employee.employeeCode,
                time_from.strftime('%Y%m%d%H%M%S'))

    @classmethod
    def delete_by_time(cls, time_from):
        query = 'Delete from FPEntries Where C_Date + C_Time >= ?'
        Connection().execute(query, time_from.strftime('%Y%m%d%H%M%S'))
