<?php

abstract class StorageDriver {
    abstract public function get($name);
    abstract public function store($name, $data);
} 

class MemcachedStorage extends StorageDriver {
    private $memcached;

    public function __construct($host, $port) {
        $this->memcached = new Memcached();
        $this->memcached->addServer($host, $port);
    }

    public function get($name) {
        return $this->memcached->get($name);
    }


    public function store($name, $data) {
        return $this->memcached->set($name, $data);
    }

    public function getMemcached() {
	return $this->memcached;
    }
}

class FileStorage extends StorageDriver {
    const STORAGE_PATH="./files/";

    public function __construct() {
    }

    public function get($name) {
        $data = file_get_contents(self::STORAGE_PATH . $name);
        return $data;
    }

    public function store($name, $data) {
        $file = fopen(self::STORAGE_PATH . $name, "w");
        $ret = fwrite($file, $data);
        fclose($file);

        return $ret;
    }
}


$driver = new MemcachedStorage("/run/memcached/memcached.sock", 0);

if($_SERVER["REQUEST_METHOD"] === "PUT") {
    // get filename, fail if none provided
    if(!isset($_GET["name"])) {
        http_response_code(400);
        exit(0);
    }

    // read put data 
    $data = file_get_contents("php://input");
    if(!$data) {
        http_response_code(500);
        exit(0);
    }

    // store data + get needed time
    $start = hrtime(true);
    $result = $driver->store($_GET["name"], $data);
    $end = hrtime(true);
    if(!$result) {
        http_response_code(500);
        exit(0);
    }

    // log needed time
    $file = fopen("./store_time.log", "a");
    fwrite($file, strval($end - $start) . "\n");
    fclose($file);
}
else if($_SERVER["REQUEST_METHOD"] === "GET") {
    if(!isset($_GET["name"])){
        http_response_code(400);
        exit(0);
    }
    
    $data = $driver->get($_GET["name"]);
    if(!$data) {
        http_response_code(404);
        exit(0);
    }

    header('Content-Type: */*');
    echo($data);
}
else {
    http_response_code(405);
}
?>
