import hassapi as hass
import datetime
import time
import dateutil.parser as dp
import math
import ast
import holidays

# Configuration Constants - Sensors
ATTR_SENSORS = "sensorentitys"
ATTR_SENSORS_LIGHT = "light"
ATTR_SENSORS_TEMPERATURE = "temperature"
ATTR_SENSORS_SUN = "sun"
ATTR_SENSORS_HOLIDAY = "holidaymode"
ATTR_SENSORS_SHUTTERSTATE = "shutterstate"

# Configuration Constants - Times
ATTR_TIMES = "times"
ATTR_TIMES_OPENFROM = "open_from"
ATTR_TIMES_OPENTO = "open_to"
ATTR_TIMES_CLOSEFROM = "close_from"
ATTR_TIMES_CLOSETO = "close_to"
ATTR_TIMES_WEEKDAY = "normal_weekday"
ATTR_TIMES_VACATIONWEEKDAY = "vacation_weekday"

# Configuration Constants - Limits
ATTR_LIMITS = "limits"
ATTR_LIMITS_TEMP = "temp"
ATTR_LIMITS_LIGHT = "light"
ATTR_LIMITS_SUN = "sun"

# Configuration Constants - scenes
ATTR_SCENES = "scenes"
ATTR_SCENES_UP = "shutterup"
ATTR_SCENES_DOWN = "shutterdown"
ATTR_SCENES_ENTITY = "entity"

# Dicts
WEEKDAY_DICT = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
REGISTERED_ENTITYS = []

#
# Base class and logic
#
class SmartShutters(hass.Hass):
    #
    # Initialize app
    #
    def initialize(self):
        self.log('Starting smart shutters')
        
        # Internal setup
        self.__holidaysBB = holidays.country_holidays('DE', subdiv='BB')
        self.__holidaysBE = holidays.country_holidays('DE', subdiv='BE')

        # Read time for movements
        self.__timeFrames = self.args[ATTR_TIMES]
        self.__parseNewTimes(self.__timeFrames, True)

        # Set scenes for shutter up and down
        self.__shutterSceneUp = []
        for scene in self.args[ATTR_SCENES][ATTR_SCENES_UP]:
            self.__shutterSceneUp.append(scene[ATTR_SCENES_ENTITY])
        self.__shutterSceneDown = []
        for scene in self.args[ATTR_SCENES][ATTR_SCENES_DOWN]:
            self.__shutterSceneDown.append(scene[ATTR_SCENES_ENTITY])

        # SensorEntitys
        self.__sensorLight = self.args[ATTR_SENSORS][ATTR_SENSORS_LIGHT]
        self.__sensorTemperature = self.args[ATTR_SENSORS][ATTR_SENSORS_TEMPERATURE]
        self.__sensorSun = self.args[ATTR_SENSORS][ATTR_SENSORS_SUN]
        self.__sensorHolidayMode = self.args[ATTR_SENSORS][ATTR_SENSORS_HOLIDAY]
        self.__shutterState = self.args[ATTR_SENSORS][ATTR_SENSORS_SHUTTERSTATE]

        # Limits
        self.__limitsLight = self.args[ATTR_LIMITS][ATTR_LIMITS_LIGHT]
        self.__limitsTemperature = self.args[ATTR_LIMITS][ATTR_LIMITS_TEMP]
        self.__limitsSun = self.args[ATTR_LIMITS][ATTR_LIMITS_SUN]
        
        # Starte alle Listener
        self.__addStateChangeListenerIfEntity(self.__sensorLight)
        self.__addStateChangeListenerIfEntity(self.__sensorTemperature)
        self.__addStateChangeListenerIfEntity(self.__sensorSun)
        self.__addStateChangeListenerIfEntity(self.__sensorHolidayMode)
        self.__addStateChangeListenerIfEntity(self.__sensorLight)
        
        # Initial update
        self.log("Ready for action...")
        self.__update()
        
        # Start timer to execute updates every minute for time frames
        time = datetime.time(0, 0, 0)
        self.run_minutely(self.__callbackMinutelyRun, time)
    
    #
    # State of entity value has changed
    #
    def state_changed(self, entity, attribute, old, new, kwargs) -> None:
        self.__parseNewTimes()
        self.__update()

    #
    # Time values are changed
    #
    def __parseNewTimes(self, timeFrames, initialize = False) -> None:
        # Read all timeframes
        self.__parsedTimes = [];
        for timeframe in timeFrames:
            # Parse times
            timeOpenFrom = time.strptime(self.__getState(timeframe[ATTR_TIMES_OPENFROM]), '%H:%M:%S')
            timeOpenTo = time.strptime(self.__getState(timeframe[ATTR_TIMES_OPENTO]), '%H:%M:%S')
            timeCloseFrom = time.strptime(self.__getState(timeframe[ATTR_TIMES_CLOSEFROM]), '%H:%M:%S')
            timeCloseTo = time.strptime(self.__getState(timeframe[ATTR_TIMES_CLOSETO]), '%H:%M:%S')
            
            # Parse weekdays
            weekdaySet = []
            if ATTR_TIMES_WEEKDAY in timeframe:
                weekdayConfig = ast.literal_eval(self.__getState(timeframe[ATTR_TIMES_WEEKDAY]))
                for weekday in weekdayConfig:
                    weekdaySet.append(WEEKDAY_DICT[weekday])
            weekdayVacationSet = []
            if ATTR_TIMES_VACATIONWEEKDAY in timeframe:
                weekdayConfig = ast.literal_eval(self.__getState(timeframe[ATTR_TIMES_VACATIONWEEKDAY]))
                for weekday in weekdayConfig:
                    weekdayVacationSet.append(WEEKDAY_DICT[weekday])
            
            # Create new structure
            newTimerSet = {
                "openFrom" : timeOpenFrom,
                "openTo" : timeOpenTo,
                "closeFrom" : timeCloseFrom,
                "closeTo" : timeCloseTo,
                "vacationdays" : weekdayVacationSet,
                "weekdays" : weekdaySet
            };
            self.__parsedTimes.append(newTimerSet)
            
            # Add listeners
            if initialize == True:
                self.__addStateChangeListenerIfEntity(timeframe[ATTR_TIMES_OPENFROM])
                self.__addStateChangeListenerIfEntity(timeframe[ATTR_TIMES_OPENTO])
                self.__addStateChangeListenerIfEntity(timeframe[ATTR_TIMES_CLOSEFROM])
                self.__addStateChangeListenerIfEntity(timeframe[ATTR_TIMES_CLOSETO])
                if ATTR_TIMES_WEEKDAY in timeframe:
                    self.__addStateChangeListenerIfEntity(timeframe[ATTR_TIMES_WEEKDAY])
                if ATTR_TIMES_VACATIONWEEKDAY in timeframe:
                    self.__addStateChangeListenerIfEntity(timeframe[ATTR_TIMES_VACATIONWEEKDAY])

    #
    # Return value of entity or direct value
    #
    def __getState(self, value):
        value = str(value).lower()
        if "." not in value:
            return value
        if not self.entity_exists(value):
            return value
        return self.get_state(value)

    #
    # Add listeners to objects if entity
    #
    def __addStateChangeListenerIfEntity(self, value) -> None:
        value = str(value).lower()
        if "." not in value:
            return
        if not self.entity_exists(value):
            return
        if value in REGISTERED_ENTITYS:
            return
        REGISTERED_ENTITYS.append(value)
        self.listen_state(self.state_changed, value)

    #
    # Minute Run
    #
    def __callbackMinutelyRun(self, payload) -> None:
        self.__update()
        
    #
    # Update current state
    #
    def __update(self):
        # Init
        currentTime = datetime.datetime.now()
        searchDayTime = time.strptime(currentTime.strftime('%H:%M:%S'), '%H:%M:%S')
        weekDay = currentTime.weekday()
        stateHolidayMode = self.get_state(self.__sensorHolidayMode)
        shutterState = self.get_state(self.__shutterState)
        action = -1;
        currentTimeFrame = 0

        # We overwrite the holiday mode
        if currentTime.date() in self.__holidaysBB:
            stateHolidayMode = "on"
        if currentTime.date() in self.__holidaysBE:
            stateHolidayMode = "on"

        # Search for timeframes, did we have one?
        for timeframe in self.__parsedTimes:
            # Check vacation mode
            if (stateHolidayMode == "on") and (weekDay not in timeframe["vacationdays"]):
                continue
            elif (stateHolidayMode != "on") and (weekDay not in timeframe["weekdays"]):
                continue
				
            # Check timeframe
            if ((timeframe["openFrom"] <= searchDayTime) and (timeframe["openTo"] >= searchDayTime)):
                currentTimeFrame = timeframe
                action = 'open'
                break
            elif ((timeframe["closeFrom"] <= searchDayTime) and (timeframe["closeTo"] >= searchDayTime)):
                currentTimeFrame = timeframe
                action = 'close'
                break
        
        # Abort here, if we have no timeframe!
        if currentTimeFrame == 0:
            return

        # Read all values
        stateLight =  self.get_state(self.__sensorLight)
        stateTemperature =  self.get_state(self.__sensorTemperature)
        stateSun =  self.get_state(self.__sensorSun)
        
        # LimitCheck
        limitHit = False
        
        # Check Limits - Sun
        if (action == 'open') and (stateSun > self.__limitsSun):
            limitHit = True
        elif (action == 'close') and (stateSun < self.__limitsSun):
            limitHit = True
            
        # Check Limits - Light
        if (action == 'open') and (stateLight > self.__limitsLight):
            limitHit = True
        elif (action == 'close') and (stateLight < self.__limitsLight):
            limitHit = True
            
        # Check Limits - Temperature
        if (action == 'open') and (stateTemperature > self.__limitsTemperature):
            limitHit = True
        elif (action == 'close') and (stateTemperature < self.__limitsTemperature):
            limitHit = True

        # Execute Shutter
        if limitHit and (action == 'open') and (shutterState == 'off'):
            self.log("shutter up")
            self.turn_on(self.__shutterState)
            for activateScene in self.__shutterSceneUp:
                self.turn_on(activateScene)

        elif limitHit and (action == 'close') and (shutterState == 'on'):
            self.log("shutter down")
            self.turn_off(self.__shutterState)
            for activateScene in self.__shutterSceneDown:
                self.turn_on(activateScene)
