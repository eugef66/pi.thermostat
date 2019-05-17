<?php



if ($_POST!=null)
{
		$pin=$_POST["pin"];
		//echo "$pin<br>";
		$salt=sha1(md5($pin));
		$hash=crypt($pin,$salt);
		//echo $hash;
		if ($hash=='bea.NhQjqJfUA')
		{
			session_start();
			$_SESSION['bea.NhQjqJfUA'] = "true";
			//echo $_SESSION['bea.NhQjqJfUA'];
			header('Location: index.php');
			exit();
		}
		else{
			session_start();
			$_SESSION = array();
			session_destroy();
		}
}

?>

<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
	"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">

<head>
	<title>Home Thermostat</title>
	<meta http-equiv="content-type" content="text/html;charset=utf-8" />
	<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
	<!-- Latest compiled and minified CSS -->
	<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/3.4.1/css/bootstrap.min.css" integrity="sha384-HSMxcRTRxnN+Bdg0JdbxYKrThecOKuH5zCYotlSAcp1+c8xmyTe9GYg1l9a69psu" crossorigin="anonymous">
	<!-- Optional theme -->
	<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/3.4.1/css/bootstrap-theme.min.css" integrity="sha384-6pzBo3FDv/PJ8r2KRkGHifhEocL+1X2rVCTTkUfGk7/0pbek5mMa1upzvWbrUbOZ" crossorigin="anonymous">
	
	<link rel="apple-touch-icon" sizes="57x57" href="/images/apple-icon-57x57.png">
	<link rel="apple-touch-icon" sizes="60x60" href="/images/apple-icon-60x60.png">
	<link rel="apple-touch-icon" sizes="72x72" href="/images/apple-icon-72x72.png">
	<link rel="apple-touch-icon" sizes="76x76" href="/images/apple-icon-76x76.png">
	<link rel="apple-touch-icon" sizes="114x114" href="/images/apple-icon-114x114.png">
	<link rel="apple-touch-icon" sizes="120x120" href="/images/apple-icon-120x120.png">
	<link rel="apple-touch-icon" sizes="144x144" href="/images/apple-icon-144x144.png">
	<link rel="apple-touch-icon" sizes="152x152" href="/images/apple-icon-152x152.png">
	<link rel="apple-touch-icon" sizes="180x180" href="/images/apple-icon-180x180.png">
	<link rel="icon" type="image/png" sizes="192x192"  href="/images/android-icon-192x192.png">
	<link rel="icon" type="image/png" sizes="32x32" href="/images/favicon-32x32.png">
	<link rel="icon" type="image/png" sizes="96x96" href="/images/favicon-96x96.png">
	<link rel="icon" type="image/png" sizes="16x16" href="/images/favicon-16x16.png">
	<link rel="manifest" href="/images/manifest.json">
	<meta name="msapplication-TileColor" content="#ffffff">
	<meta name="msapplication-TileImage" content="/images/ms-icon-144x144.png">
	<meta name="theme-color" content="#ffffff">
	
	
</head>

<body>
<form action="login.php" method="POST">
	<div class="jumbotron text-center">	
		<p>
		<input type="number" pattern="[0-9]*" name="pin" placeholder="PIN" class="form-control input-lg"/>
		</p>
		<button type="submit" class="btn btn-primary btn-lg">OK</button>
	</div>
</form>
</body>

</html>
