schAction = "OFF";

function doSubmit(mode, isSchedule) {
	/*schedule:
		null - reset
		true - set
		false - keep
	*/
	var schedule = document.getElementById('schedule').value;
	if (isSchedule == null) {
		schedule = "";
	}
	else if (isSchedule) {
		sch_date = document.getElementById('sch_date').value;
		sch_time_h = document.getElementById('sch_time_h').value;
		sch_time_m = document.getElementById('sch_time_m').value;
		schedule = sch_date + " " + sch_time_h + ":" + sch_time_m;
		//alert(schAction + " : " + schedule);
	}
	var mode = (mode == null ? document.getElementById('mode').value : mode);
	var targetTemp = document.getElementById('targetTemp');
	var temp = (targetTemp == null ? document.getElementById('temp').value : targetTemp.value);
	var url = "/set/" + mode + "/" + temp + "?sch=" + (schedule ? schedule : "");
	//alert (url);
	location.replace(url);
}